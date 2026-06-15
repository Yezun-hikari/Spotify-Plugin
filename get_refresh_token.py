import spotipy
from spotipy.oauth2 import SpotifyOAuth
import sys

print("=== Spotify Refresh Token Generator ===")
print("To use the Spotify plugin without needing to log in every hour, you need a Refresh Token.")
print("A Refresh Token allows the plugin to generate new access tokens in the background.")
print("\nInstructions:")
print("1. Go to the Spotify Developer Dashboard (https://developer.spotify.com/dashboard)")
print("2. Create an App, and edit settings to add 'http://localhost:8080' to the Redirect URIs.")
print("3. Copy your Client ID and Client Secret.")
print("")

client_id = input("Enter your Client ID: ").strip()
client_secret = input("Enter your Client Secret: ").strip()

if not client_id or not client_secret:
    print("Client ID and Client Secret are required.")
    sys.exit(1)

scope = "user-read-currently-playing user-read-playback-state"

try:
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8080",
        scope=scope,
        open_browser=False
    )

    url = auth_manager.get_authorize_url()
    print("\n[Action Required]")
    print("Please open this URL in your browser, log in, and accept the permissions:")
    print("-" * 50)
    print(url)
    print("-" * 50)
    print("\nAfter accepting, you will be redirected to an empty or error page at localhost.")
    print("Look at the URL in your browser's address bar. It will look like this:")
    print("http://localhost:8080/?code=NApCCgB...&state=...")
    
    redirected_url = input("\nPaste the FULL redirected URL here: ").strip()
    
    code = auth_manager.parse_response_code(redirected_url)
    if not code:
        print("Error: Could not extract code from URL.")
        sys.exit(1)
        
    token_info = auth_manager.get_access_token(code, as_dict=True)
    refresh_token = token_info.get("refresh_token")
    
    if refresh_token:
        print("\n" + "=" * 50)
        print("SUCCESS! Here is your Refresh Token:")
        print(refresh_token)
        print("=" * 50)
        print("Copy this Refresh Token and paste it into the Pixoo Hub Marketplace settings for the Spotify Plugin.")
    else:
        print("\nError: Could not obtain refresh token.")
        
except Exception as e:
    print(f"\nAn error occurred: {e}")
