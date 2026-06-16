import os
import time
import logging
import requests
from io import BytesIO
from PIL import Image
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from app.plugin_api import PixooPluginBase

logger = logging.getLogger(__name__)

class HeadlessSpotifyOAuth(SpotifyOAuth):
    def _get_auth_response_interactive(self, open_browser=False):
        # Override to prevent `input()` from blocking the server thread!
        raise Exception("Refresh token is invalid or expired! Interactive login is blocked on this headless server.")

class SpotifyPlugin(PixooPluginBase):
    def setup(self):
        self.client_id = self.config.get("client_id", "")
        self.client_secret = self.config.get("client_secret", "")
        self.refresh_token = self.config.get("refresh_token", "")
        self.show_progress_bar = str(self.config.get("show_progress_bar", "false")).lower() == "true"
        self.update_interval = max(1, int(self.config.get("update_interval", 3)))
        
        self.sp = None
        self.last_track_id = None
        self.cover_path = os.path.join(os.path.dirname(__file__), "spotify_cover.png")
        self.pixoo = self.get_pixoo_instance()

        if not (self.client_id and self.client_secret and self.refresh_token):
            logger.warning("Spotify credentials missing. Please configure them in settings.")
            return

        try:
            scope = "user-read-currently-playing user-read-playback-state"
            token_info = {
                "refresh_token": self.refresh_token,
                "access_token": "dummy",
                "expires_at": 0,
                "scope": scope
            }
            auth_manager = HeadlessSpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri="https://google.com/callback",
                cache_handler=MemoryCacheHandler(token_info=token_info),
                open_browser=False,
                scope=scope
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            logger.info("Spotify client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Spotify client: {e}")

    def update_display(self, playback):
        if not playback or not playback.get('item') or not playback.get('is_playing'):
            if self.last_track_id is not None:
                self.release_screen()
                self.last_track_id = None
            return

        item = playback['item']
        track_id = item.get('id')
        
        # Check if track changed to fetch new cover
        if track_id != self.last_track_id:
            self.last_track_id = track_id
            images = item.get('album', {}).get('images', [])
            if images:
                # Use the smallest image to save memory and bandwidth (usually the last one is 64x64)
                img_url = images[-1].get('url')
                try:
                    response = requests.get(img_url, timeout=5)
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content))
                    # Ensure it's exactly 64x64 if it's not already
                    if img.size != (64, 64):
                        img = img.resize((64, 64), Image.Resampling.LANCZOS)
                    img.save(self.cover_path)
                except Exception as e:
                    logger.error(f"Error downloading cover: {e}")
                    
        # Draw onto Pixoo buffer
        self.pixoo.fill((0, 0, 0))
        try:
            if os.path.exists(self.cover_path):
                self.pixoo.draw_image(self.cover_path)
            else:
                self.pixoo.draw_text("Spotify", (15, 25), (30, 215, 96))
            
            if self.show_progress_bar:
                duration_ms = max(1, item.get('duration_ms', 1))
                progress_ms = playback.get('progress_ms', 0)
                bar_width = int(min(1.0, max(0.0, progress_ms / duration_ms)) * 64)
                if bar_width > 0:
                    self.pixoo.draw_line((0, 63), (bar_width - 1, 63), (0, 120, 255))
            
            self.pixoo.push()
        except Exception as e:
            logger.error(f"Error drawing to pixoo: {e}")

    def loop(self):
        while True:
            if self.sp:
                try:
                    playback = self.sp.current_playback()
                    self.update_display(playback)
                except Exception as e:
                    logger.error(f"Plugin loop error: {e}")
            time.sleep(self.update_interval)

