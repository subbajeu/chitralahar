Watermark fonts
===============

Drop .ttf or .otf font files in this folder and they appear in the watermark
font picker (Settings -> Watermark). The filename (without extension) becomes the
display name, e.g. "Playfair Display.ttf" -> "Playfair Display".

The app also always offers a built-in default sans-serif, so this folder may be
empty.

Licensing: only font files YOU are licensed to use/redistribute belong here.
Great free (SIL Open Font License) choices from https://fonts.google.com:
  - Playfair Display, Cormorant, EB Garamond  (elegant serif)
  - Inter, Montserrat, Raleway                (clean sans)
  - Great Vibes, Dancing Script               (script / signature)

Note: operating-system fonts (e.g. macOS/Windows system fonts) are usually NOT
redistributable — fine to use on your own server, but don't commit them to a
public repository. This folder's font files are git-ignored for that reason.
