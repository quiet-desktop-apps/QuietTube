"""User-facing setup steps, shared by the native setup panel and tests.

Checked against Google Auth Platform documentation on 8 November 2026.
No application registration or account-specific data belongs in this module.
"""

SCOPES_TEXT = "https://www.googleapis.com/auth/youtube.force-ssl"
SETUP_STEPS = (
    ("1. Create your personal project", "https://console.cloud.google.com/projectcreate",
     "Project name: QuietTube Personal (or a name you recognize). Select that same project on every page below. "
     "YouTube Data API does not require paid billing; check that this project is not linked to your existing billing account. "
     "Your organization's administrator may restrict project creation."),
    ("2. Enable YouTube Data API v3", "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
     "Check your project in the top selector, then choose Enable. You do not need an API key for this OAuth connection."),
    ("3. Configure the consent screen", "https://console.cloud.google.com/auth/branding",
     "Google Auth Platform → Branding → Get started (if shown). App name: QuietTube Personal. "
     "User support email and contact email: your own email. For a personal Gmail account choose External as the audience. "
     "Review Google's terms, then create the configuration. Use accurate information; do not enter QuietTube maintainer contact details."),
    ("4. Add yourself as a test user", "https://console.cloud.google.com/auth/audience",
     "Audience → Testing → Test users → Add users: enter the Google email you will sign in with. "
     "Testing access for YouTube scopes expires after seven days; you may need to sign in again. "
     "Publishing and verification have additional requirements and are not a promise of permanent access."),
    ("5. Add the YouTube scope", "https://console.cloud.google.com/auth/scopes",
     "Data Access → Add or remove scopes → manually add the scope shown below, then Update/Save. "
     "It supports reading account feeds and the Like action. Google's permission description is broader than those features; "
     "review it before approving access. QuietTube does not upload or delete videos."),
    ("6. Create a Desktop client", "https://console.cloud.google.com/auth/clients",
     "Clients → Create client. Application type: Desktop app. Name: QuietTube on my computer. "
     "Choose Create, then Download JSON. Keep the file outside the repository, for example in Downloads. "
     "A Desktop client does not need a website URL or a manually configured redirect URI; QuietTube uses a temporary local callback."),
    ("7. Import here, then sign in", None,
     "Use Import Desktop JSON below. Alternatively copy Client ID and Client secret from that same Desktop client "
     "into the two matching fields, then Save to keyring. Paste neither an API key, project ID, Google password nor access token. "
     "Then choose Sign in with Google. Check that the consent screen identifies your own project. "
     "You may close the browser afterward; account requests use OAuth, not copied browser cookies."),
)

STORAGE_TEXT = (
    "Saved client configuration and tokens stay in your desktop Secret Service keyring, not in the checkout, "
    "SQLite database or an exported JSON file. Use a password-protected login keyring. If it is unavailable, "
    "saving fails without a plaintext fallback. The downloaded Google JSON remains wherever you saved it; "
    "QuietTube does not remove that original file. Keep it private and outside GitHub."
)
LIMITS_TEXT = (
    "Experimental: live account reliability and daily quota usage are not yet verified. Home becomes recent subscription uploads; "
    "Watch Later is unavailable through this API. Shorts may appear. OAuth does not authenticate mpv or fix playback errors. "
    "Your project has its own limited quota, not unlimited access. Google's distribution and playback policy questions remain unresolved. "
    "Browser-session import remains available as a separate choice."
)
