# Bundled Fonts

This directory must contain TTF font files used by the poster renderer.
Fonts are bundled so the bot works consistently on Railway, Render, and Docker
without relying on system fonts.

## Required Files

Download and place these files here:

| Filename                  | Source                                           |
|---------------------------|--------------------------------------------------|
| `Poppins-Regular.ttf`     | https://fonts.google.com/specimen/Poppins        |
| `Poppins-SemiBold.ttf`    | https://fonts.google.com/specimen/Poppins        |
| `Poppins-Bold.ttf`        | https://fonts.google.com/specimen/Poppins        |
| `Inter-Regular.ttf`       | https://fonts.google.com/specimen/Inter          |
| `Inter-SemiBold.ttf`      | https://fonts.google.com/specimen/Inter          |

All fonts are licensed under the **SIL Open Font License (OFL)** and are free
to use commercially.

## Quick Download (Linux / macOS / Railway build step)

```bash
pip install gfonts   # or use curl

# Or download directly:
curl -L "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf" \
     -o fonts/Poppins-Regular.ttf

curl -L "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf" \
     -o fonts/Poppins-SemiBold.ttf

curl -L "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf" \
     -o fonts/Poppins-Bold.ttf

curl -L "https://github.com/google/fonts/raw/main/ofl/inter/Inter-Regular.ttf" \
     -o fonts/Inter-Regular.ttf

curl -L "https://github.com/google/fonts/raw/main/ofl/inter/Inter-SemiBold.ttf" \
     -o fonts/Inter-SemiBold.ttf
```

## Fallback

If a font file is missing, the renderer falls back to `Poppins-Regular.ttf`,
then to PIL's built-in bitmap font. Output will still be generated but may
look less polished.
