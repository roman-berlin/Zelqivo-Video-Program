# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately, either way:

- GitHub: *Security → Report a vulnerability* (private advisory) on this repo
- Email: romario.berlin@gmail.com with subject starting `[SECURITY]`

You will get an acknowledgement within **7 days**. Please include steps to
reproduce and, if possible, a sample input file. Coordinated disclosure:
we'll agree on a timeline with you before anything is published; credit is
given unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes.

## Honest attack-surface notes

So you know where to look:

- The app **shells out to `ffmpeg`/`ffprobe` with user-supplied file paths**
  (no `shell=True` anywhere, arguments are passed as lists — but path and
  metadata handling is the main surface).
- Media files are parsed by FFmpeg, OpenCV, and librosa — a malicious media
  file attacking those parsers attacks this app.
- The optional AI extras download models from Hugging Face at the user's
  explicit request.
- The app makes no other network connections and has no server component.
