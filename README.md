# Spotify Now Playing Plugin

This plugin for the Pixoo Hub Marketplace displays the cover art of the currently playing song on your Spotify account directly on your Pixoo 64. It also features an optional blue progress bar at the bottom of the screen.

## 🛠 Configuration & Setup

Because this plugin interacts with the Spotify API to read your current playback, you need to provide it with your own API credentials. This ensures you don't run into rate limits shared by other users.

### Step 1: Create a Spotify Developer App
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Log in with your Spotify account and click on **Create app**.
3. Fill out the details (App Name and Description can be anything).
4. Under **Redirect URIs**, you **must** enter `http://localhost:8080`.
5. Under **APIs used**, check **Web API**.
6. Save the app. 
7. Go to the app's settings and click **View client secret**. You will need both the **Client ID** and **Client Secret** for the next steps.

### Step 2: Get your Refresh Token
To allow the Pixoo Hub to keep updating your screen in the background without asking you to log in every hour, the plugin needs a **Refresh Token**.

Included in this plugin is a helper script to generate this token:
1. Open a terminal/command prompt in the plugin's folder.
2. Ensure you have the required library installed:
   ```bash
   pip install spotipy
   ```
3. Run the script:
   ```bash
   python get_refresh_token.py
   ```
4. Paste your **Client ID** and **Client Secret** when prompted.
5. Your browser will open. Log into Spotify and click "Agree".
6. You will be redirected to an empty page or a "site can't be reached" error. **This is normal.**
7. Look at the URL in your browser's address bar. It will look like `http://localhost:8080/?code=NApCC...`. Copy the **entire URL**.
8. Paste the URL back into the python script.
9. The script will output your **Refresh Token**. Copy it!

### Step 3: Configure the Plugin in Pixoo Hub
Open the Pixoo Hub dashboard, install this plugin, and navigate to the plugin's settings.

- **Client ID**: Paste the Client ID from Step 1.
- **Client Secret**: Paste the Client Secret from Step 1.
- **Refresh Token**: Paste the Refresh Token you got in Step 2.
- **Show Progress Bar**: Enter `true` to display a 1-pixel blue progress bar at the bottom, or `false` to hide it.
- **Update Interval (seconds)**: Defines how often the plugin asks Spotify for the current song. `3` is a good default.

Once saved, the plugin will authenticate automatically and your Pixoo 64 will display your current song's cover!
