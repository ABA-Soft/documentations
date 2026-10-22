# FIDE Test Development user guide

- `fide-test-development-user-guide.html` – the finished, self-contained guide (images embedded). Opens in any browser, works offline.
- `src/guide.src.html` – the text and the page source; screenshot slots are marked with `data-shot="name"`.
- `src/images/*.webp` – screenshots (1560×900 view, light theme, local test data).
- `src/build.py` – embeds the images and rewrites the finished file: `cd src && python3 build.py` (needs Pillow).

To replace a screenshot, overwrite `src/images/<name>.webp` and run the build again.
