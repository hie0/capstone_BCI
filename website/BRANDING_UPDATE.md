# NEUROLINK branding update

## Changes

- `src/components/BrandLogo.tsx`: one shared, full image logo for Header and Footer. Original wordmark and MI-BCI RESEARCH LAB are part of the supplied image, with no duplicate HTML text.
- `src/main.tsx`: replaced only the old branding BrainCircuit icon/text. Both logos link home. School/project descriptions and functional icons remain intact.
- `src/styles.css`: logo dimensions/aspect ratio and mobile Footer fitting. Header remains 80px desktop / 112px mobile.
- `index.html`: 16/32/48px PNG favicon, multi-resolution ICO and 180px Apple Touch Icon. Relative `%BASE_URL%` paths support GitHub Pages and Vercel.
- `public/brand/`: untouched copies `neurolink-logo.png` and `neurolink-symbol.png`; cropped/resized display logo `neurolink-logo-header.png`; all requested favicon files and `asset-info.json` provenance.
- `scripts/generate-brand-assets.mjs`: reproducible asset conversion using the supplied PNGs. No generated/redesigned artwork. Near-transparent outer padding is ignored for crop bounds; original copies remain byte-identical. Output images preserve aspect ratio and alpha. Display PNG: 720×184, 101,630 bytes (about 99KiB), versus the 488,286-byte source logo.
- `src/components/recordedWaveformEngine.ts`: channel labels now use uniform device-pixel scaling, separate from the signal's independently scaled axes. A fixed label gutter prevents names from touching the waveform.
- `tests/branding.spec.ts`: original SHA256 preservation, icon sizes, common Header/Footer images, aspect ratio, unchanged Header heights, logo navigation and prefixed deployment path.
- `tests/recorded-waveform.spec.ts`: verifies all channel-name drawing transforms have equal horizontal/vertical scale while the measured EEG waveform and pause/resume remain correct.
- `playwright.static.config.ts`: includes branding verification.

Original images supplied from the workspace remain unchanged. No research results, data, EEG models, Backend, 3D assets or functional feature icons were changed by this branding work. Earlier uncommitted game/waveform work remains separate in the working tree.

## Validation

- Production build passed.
- Original asset hashes match the provided PNGs.
- Favicon PNG dimensions are exactly 16, 32, 48 and 180 square pixels; ICO includes 16, 32 and 48px entries.
- Desktop 1440px / mobile 390px Header and Footer fit their containers; logos do not overlap navigation and retain 720:184 aspect ratio.
- Shared logo links navigate to home.
- `/capstone_BCI/` prefixed asset loading passed.
- Recorded waveform browser test passed: measured values, equal label transform scales, worker frame timing, pause/resume/reset.
- Browser screenshots: ignored `backend/local_cache/branding/header-{1440,390}.png`, `footer-{1440,390}.png`, `favicon-preview.png`.

Existing separate issue: the Communication Board's internal mobile progress/actions strip overflows the viewport. This is outside the branding scope; its component/layout was preserved. Common Header/Footer branding fits correctly even on that page.

No commit, push or production publishing was performed.

## Regenerate

From `website/`:

```sh
node scripts/generate-brand-assets.mjs /path/to/뉴로링크_뇌파_연구_로고_2.png /path/to/a_clean_flat_vector_icon_on_a_transparent_backgrou.png
```

If output assets change, update their cache-version query in `BrandLogo.tsx` and `index.html` to avoid stale browser favicons.
