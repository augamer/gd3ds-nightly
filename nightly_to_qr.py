#!/usr/bin/env python3
"""
nightly_to_qr.py
Baixa ZIP do nightly.link, extrai .cia/.3dsx,
deleta upload anterior no Catbox, sobe o novo,
atualiza redirect.json e gera QR Code.

Uso local:
    pip install requests qrcode[pil]
    python nightly_to_qr.py <NIGHTLY_URL> <CATBOX_USERHASH> [arquivo_anterior.cia]

No GitHub Actions as variáveis vêm de env vars:
    NIGHTLY_URL, CATBOX_USERHASH, REDIRECT_URL, PREV_CATBOX_FILE
"""

import os
import sys
import json
import zipfile
import io
import requests
import qrcode
from pathlib import Path

HOMEBREW_EXTENSIONS = (".3dsx", ".cia")
CATBOX_API          = "https://catbox.moe/user/api.php"


# ── 1. Baixa o ZIP ──────────────────────────────────────────────────────────
def download_zip(url: str) -> bytes:
    print(f"[1/5] Baixando ZIP: {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    print(f"      ✓ {len(r.content)/1024:.1f} KB")
    return r.content


# ── 2. Extrai homebrew ───────────────────────────────────────────────────────
def extract_homebrew(zip_bytes: bytes) -> tuple[str, bytes]:
    print("[2/5] Extraindo .cia / .3dsx...")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(HOMEBREW_EXTENSIONS):
                data = zf.read(name)
                filename = Path(name).name
                print(f"      ✓ {filename} ({len(data)/1024:.1f} KB)")
                return filename, data
    raise FileNotFoundError("Nenhum .cia/.3dsx encontrado no ZIP.")


# ── 3. Deleta upload anterior ────────────────────────────────────────────────
def delete_catbox(userhash: str, filename: str):
    """filename = só o nome do arquivo, ex: gd3ds.cia (não a URL inteira)"""
    if not filename:
        print("[3/5] Nenhum arquivo anterior para deletar.")
        return
    print(f"[3/5] Deletando arquivo anterior: {filename}")
    r = requests.post(CATBOX_API, data={
        "reqtype":  "deletefiles",
        "userhash": userhash,
        "files":    filename,
    }, timeout=30)
    r.raise_for_status()
    print(f"      ✓ Deletado: {r.text.strip()}")


# ── 4. Upload no Catbox ──────────────────────────────────────────────────────
def upload_catbox(userhash: str, filename: str, data: bytes) -> str:
    print(f"[4/5] Fazendo upload de '{filename}'...")
    r = requests.post(CATBOX_API, data={
        "reqtype":  "fileupload",
        "userhash": userhash,
    }, files={"fileToUpload": (filename, data)}, timeout=120)
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Catbox retornou: {url!r}")
    print(f"      ✓ {url}")
    return url


# ── 5. Atualiza redirect.json ────────────────────────────────────────────────
def update_redirect_json(direct_url: str, filename: str, path="redirect.json"):
    payload = {
        "url":      direct_url,
        "filename": filename,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"      ✓ redirect.json atualizado → {direct_url}")


# ── 6. Gera QR Code ──────────────────────────────────────────────────────────
def generate_qr(redirect_url: str, output="qrcode.png"):
    print(f"[5/5] Gerando QR Code → {output}")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(redirect_url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(output)
    print(f"      ✓ Salvo em {output}")
    return output


# ── Pipeline ─────────────────────────────────────────────────────────────────
def run():
    nightly_url   = os.environ.get("NIGHTLY_URL")   or (sys.argv[1] if len(sys.argv) > 1 else None)
    userhash      = os.environ.get("CATBOX_USERHASH") or (sys.argv[2] if len(sys.argv) > 2 else None)
    redirect_url  = os.environ.get("REDIRECT_URL")  or ""   # URL fixa do GitHub Pages
    prev_file     = os.environ.get("PREV_CATBOX_FILE") or (sys.argv[3] if len(sys.argv) > 3 else "")

    if not nightly_url or not userhash:
        print("Uso: python nightly_to_qr.py <NIGHTLY_URL> <CATBOX_USERHASH> [arquivo_anterior]")
        print("     Ou defina NIGHTLY_URL e CATBOX_USERHASH como variáveis de ambiente.")
        sys.exit(1)

    zip_bytes          = download_zip(nightly_url)
    filename, hw_bytes = extract_homebrew(zip_bytes)

    delete_catbox(userhash, prev_file)

    direct_url = upload_catbox(userhash, filename, hw_bytes)

    update_redirect_json(direct_url, filename)

    qr_target = redirect_url if redirect_url else direct_url
    generate_qr(qr_target)

    # Salva nome do arquivo novo para o próximo run deletar
    with open("catbox_current_file.txt", "w") as f:
        f.write(Path(direct_url).name)

    print("\n" + "═"*50)
    print("  CONCLUÍDO!")
    print(f"  Arquivo  : {filename}")
    print(f"  Download : {direct_url}")
    print(f"  QR aponta: {qr_target}")
    print("═"*50)


if __name__ == "__main__":
    run()
