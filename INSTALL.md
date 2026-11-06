# ENPlayer install korar niyom

Kono technical gyan lagbe na. Nicher dhap gulo follow korun.

---

## 🪟 Windows (10 / 11)

1. **`ENPlayer-Setup-1.4.4.exe`** file ta download korun.
2. File ta te **double-click** korun.
3. "Windows protected your PC" lekha nil screen ashle **More info** e click kore **Run anyway** chapun.
   (App ta notun, tai Windows chene na. Eta swabhabik.)
4. **Next → Next → Install → Finish** chapun. Admin password lagbe na.
5. Desktop ba Start menu theke **ENPlayer** khulun.

**Uninstall:** Settings → Apps → ENPlayer → Uninstall.

---

## 🐧 Ubuntu (22.04 / 24.04)

1. **`enplayer_1.4.4_all.deb`** file ta download korun.
2. File ta te **right-click** kore **Open with App Center** (ba **Software Install**) select korun.
3. **Install** chapun, apnar password din.
4. App list e **ENPlayer** search kore khulun.

> Double-click e kaj na korle Terminal khule (Ctrl+Alt+T) eta likhun:
> ```
> sudo apt install ~/Downloads/enplayer_1.4.4_all.deb
> ```

**Uninstall:** Terminal e likhun `sudo apt remove enplayer`

---

## Prothombar khulle

- Apnar **Videos** folder automatic add hoye jabe, video gulo nije nije chole ashbe.
- Onno folder add korte upore **＋** button e click korun.
- Video r upor mouse rakhle **preview** dekhabe, click korle **play** hobe.
- Kono file direct chalate: **Ctrl+O**, ba file ta window e **tene ene chere din** (drag & drop).
- Windows e video file e right-click → **Open with → ENPlayer** dieo chalano jay.

### Player shortcut

| Button | Kaj |
|---|---|
| Space | Play / Pause |
| ← → | 5 second pichone / samne |
| ↑ ↓ | Volume |
| F ba double-click | Full screen |
| Esc | Full screen theke ber hon / library te ferot |
| M | Mute |
| S / A | Subtitle / audio track bodlan |
| N / P | Porer / ager video |

Shob shortcut dekhte app er vitore **Ctrl+?** chapun.

---

## Developer der jonno: installer banano

**Shobcheye shohoj upay (GitHub):** project ta GitHub e push korun. `.github/workflows/build.yml`
nije nije Windows `.exe` installer ar Ubuntu `.deb` banabe (Actions tab → latest run → Artifacts).
`v1.0.0` er moto ekta tag push korle duita file shoho ekta Release page o toiri hobe. Shei link ta
shobaike dite parben.

**Nijer machine e:**
- Ubuntu `.deb`: `bash packaging/build-deb.sh` → `dist/enplayer_1.4.4_all.deb`
- Windows `.exe`: Windows PC te [MSYS2](https://www.msys2.org) install korun, **UCRT64** shell khule
  `bash packaging/windows/build-windows.sh` chalan. Tarpor [Inno Setup](https://jrsoftware.org/isinfo.php)
  die `packaging/windows/enplayer.iss` compile korun → `dist/ENPlayer-Setup-1.4.4.exe`
