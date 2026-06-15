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

class SpotifyPlugin(PixooPluginBase):
    def setup(self):
        self.client_id = self.config.get("client_id", "")
        self.client_secret = self.config.get("client_secret", "")
        self.refresh_token = self.config.get("refresh_token", "")
        self.show_progress_bar = str(self.config.get("show_progress_bar", "false")).lower() == "true"
        self.update_interval = int(self.config.get("update_interval", 3))

        self.sp = None
        if self.client_id and self.client_secret and self.refresh_token:
            try:
                token_info = {
                    "refresh_token": self.refresh_token,
                    "access_token": "dummy",
                    "expires_at": 0
                }
                cache_handler = MemoryCacheHandler(token_info=token_info)
                auth_manager = SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri="https://localhost:8080",
                    cache_handler=cache_handler
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify client: {e}")
        else:
            logger.warning("Spotify credentials missing. Please configure them in settings.")

        self.pixoo = self.get_pixoo_instance()
        self.last_track_id = None
        self.cover_path = os.path.join(os.path.dirname(__file__), "spotify_cover.png")

    def get_currently_playing(self):
        if not self.sp:
            return None
        try:
            return self.sp.current_playback()
        except Exception as e:
            logger.error(f"Error fetching playback: {e}")
            return None

    def update_display(self, current_playback):
        if not current_playback or not current_playback.get('item') or not current_playback.get('is_playing'):
            if self.last_track_id is not None:
                self.release_screen()
                self.last_track_id = None
            return

        item = current_playback['item']
        track_id = item.get('id')
        progress_ms = current_playback.get('progress_ms', 0)
        duration_ms = item.get('duration_ms', 1)
        
        # Check if track changed to fetch new cover
        if track_id != self.last_track_id:
            self.last_track_id = track_id
            
            images = item.get('album', {}).get('images', [])
            if images:
                img_url = images[0].get('url')
                try:
                    response = requests.get(img_url, timeout=5)
                    if response.status_code == 200:
                        img = Image.open(BytesIO(response.content))
                        img = img.resize((64, 64), Image.Resampling.LANCZOS)
                        img.save(self.cover_path)
                except Exception as e:
                    logger.error(f"Error downloading cover: {e}")
                    
        # Now draw onto Pixoo buffer
        self.pixoo.fill((0, 0, 0))
        try:
            if os.path.exists(self.cover_path):
                self.pixoo.draw_image(self.cover_path)
            else:
                # Fallback if cover doesn't exist
                self.pixoo.draw_text("Spotify", (15, 25), (30, 215, 96))
            
            # Draw progress bar if enabled
            if self.show_progress_bar:
                percent = min(1.0, max(0.0, progress_ms / duration_ms))
                bar_width = int(percent * 64)
                if bar_width > 0:
                    self.pixoo.draw_line((0, 63), (bar_width - 1, 63), (0, 120, 255))
            
            self.pixoo.push()
        except Exception as e:
            logger.error(f"Error drawing to pixoo: {e}")

    def loop(self):
        while True:
            try:
                playback = self.get_currently_playing()
                self.update_display(playback)
            except Exception as e:
                logger.error(f"Plugin loop error: {e}")
                
            time.sleep(self.update_interval)
