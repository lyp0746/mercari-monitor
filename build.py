"""
Build and Package Tool
Usage: 
  uv run python build.py --desktop    # Build desktop EXE
  uv run python build.py --web         # Build web frontend
  uv run python build.py --all         # Build all
  uv run python build.py --clean       # Clean cache
"""

import argparse
import subprocess
import sys
import os
import shutil

def check_pyinstaller():
    """Check and install PyInstaller if needed"""
    try:
        result = subprocess.run(
            ["uv", "pip", "show", "pyinstaller"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("[INFO] Installing PyInstaller...")
            result = subprocess.run(
                ["uv", "pip", "install", "pyinstaller"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("[OK] PyInstaller installed")
            else:
                print(f"[ERROR] {result.stderr}")
                return False
    except Exception as e:
        print(f"[ERROR] Failed to install PyInstaller: {e}")
        return False
    return True

def build_desktop():
    """Build desktop application to EXE"""
    print("\n" + "=" * 50)
    print("  Building Desktop Application (EXE)")
    print("=" * 50 + "\n")
    
    if not check_pyinstaller():
        return False
    
    print("[STEP 1/3] Generating spec file...")
    
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
import os
sys.setrecursionlimit(5000)

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/gui/styles.py', 'src/gui'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'PIL',
        'PIL._tkinter_finder',
        'httpx',
        'curl_cffi',
        'asyncio',
        'json',
        'sqlite3',
        'ecdsa',
        'jose',
        'passlib',
        'dateutil',
        'plyer',
        'fastapi',
        'uvicorn',
        'pydantic',
        'starlette',
        'src.config',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 单文件模式：生成一个独立的EXE，包含所有依赖
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,      # 包含二进制文件（DLL等）
    a.zipfiles,       # 包含压缩文件
    a.datas,          # 包含数据文件
    [],
    name='二手监控助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],   # 排除upx压缩的文件（避免某些DLL问题）
    runtime_tmpdir=None,
    console=False,    # 不显示控制台窗口
    windowed=True,    # Windows窗口模式
    disable_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,        # 可以添加图标路径，如: icon='icon.ico'
)
'''
    
    with open('monitor.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print("[OK] Spec file created\n")
    
    print("[STEP 2/3] Compiling (this may take 5-10 minutes)...")
    
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "monitor.spec", "--clean", "--noconfirm"]
    )
    
    if result.returncode != 0:
        print("\n[ERROR] Build failed!")
        return False
    
    print("\n[STEP 3/3] Verifying output...")

    # 单文件模式：EXE直接在dist目录下
    exe_path = os.path.join("dist", "二手监控助手.exe")

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"\n{'=' * 60}")
        print(f"  [SUCCESS] 单文件打包完成！")
        print(f"{'=' * 60}")
        print(f"\n  ★ 输出文件: dist\\二手监控助手.exe")
        print(f"  ★ 文件大小: {size_mb:.1f} MB")
        print(f"\n  ✅ 这个EXE可以直接发给客户使用！")
        print(f"     不需要其他任何文件，双击即可运行！")
        return True
    else:
        # 兼容旧版本：检查文件夹模式
        old_exe_path = os.path.join("dist", "二手监控助手", "二手监控助手.exe")
        if os.path.exists(old_exe_path):
            print(f"\n[WARNING] 使用了文件夹模式，建议重新打包为单文件")
            return True
        print("\n[ERROR] Output file not found!")
        print("         请检查错误信息并重试")
        return False

def build_web():
    """Build web frontend to static files"""
    print("\n" + "=" * 50)
    print("  Building Web Frontend")
    print("=" * 50 + "\n")
    
    # Check Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        node_version = result.stdout.strip()
        print(f"[INFO] Node.js version: {node_version}")
    except FileNotFoundError:
        print("[ERROR] Node.js not found! Please install Node.js 18+")
        print("       Download: https://nodejs.org/")
        return False
    
    # Check npm dependencies
    web_node_modules = os.path.join("web", "node_modules")
    if not os.path.exists(web_node_modules):
        print("[INFO] Installing frontend dependencies (first time)...")
        os.chdir("web")
        result = subprocess.run([sys.executable, "npm", "install"])
        os.chdir("..")
        if result.returncode != 0:
            print("[ERROR] npm install failed!")
            return False
    
    # Build
    print("[INFO] Building production version...")
    os.chdir("web")
    result = subprocess.run([sys.executable, "npm", "run", "build"])
    os.chdir("..")
    
    if result.returncode != 0:
        print("\n[ERROR] Web build failed!")
        return False
    
    # Copy to dist
    dist_web = os.path.join("dist", "web")
    web_dist = os.path.join("web", "dist")
    
    if os.path.exists(dist_web):
        shutil.rmtree(dist_web)
    
    shutil.copytree(web_dist, dist_web)
    
    print(f"\n{'=' * 50}")
    print(f"  [SUCCESS] Web Build Completed!")
    print(f"{'=' * 50}")
    print(f"\n  Output: dist\\web\\")
    print(f"\n  Deploy:")
    print(f"    1. Copy dist\\web\\ to web server")
    print(f"    2. Start API: uv run uvicorn src.api.main:app --port 8000")
    return True

def clean_cache():
    """Clean build cache"""
    print("\n" + "=" * 50)
    print("  Cleaning Build Cache")
    print("=" * 50 + "\n")
    
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = ["*.spec"]
    
    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[OK] Removed: {d}/")
    
    import glob
    for pattern in files_to_clean:
        for f in glob.glob(pattern):
            os.remove(f)
            print(f"[OK] Removed: {f}")
    
    # Clean subdirectories
    for root, dirs, files in os.walk("."):
        for d in dirs:
            if d == "__pycache__":
                full_path = os.path.join(root, d)
                shutil.rmtree(full_path)
                print(f"[OK] Removed: {full_path}")
    
    print("\n[OK] Cache cleaned!")

def main():
    parser = argparse.ArgumentParser(
        description="Build and Package Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --desktop     Build desktop EXE
  %(prog)s --web          Build web static files
  %(prog)s --all          Build both
  %(prog)s --clean        Remove build cache
        """
    )
    
    parser.add_argument("--desktop", action="store_true", help="Build desktop EXE")
    parser.add_argument("--web", action="store_true", help="Build web frontend")
    parser.add_argument("--all", action="store_true", help="Build all targets")
    parser.add_argument("--clean", action="store_true", help="Clean build cache")
    
    args = parser.parse_args()
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    if args.clean:
        clean_cache()
    elif args.all:
        success_desktop = build_desktop()
        success_web = build_web()
        
        if success_desktop and success_web:
            print(f"\n{'=' * 50}")
            print(f"  [SUCCESS] All Builds Completed!")
            print(f"{'=' * 50}")
            print(f"\n  Output:")
            print(f"    dist\\二手监控助手\\   (Desktop EXE)")
            print(f"    dist\\web\\          (Web Static)")
    elif args.desktop:
        build_desktop()
    elif args.web:
        build_web()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()