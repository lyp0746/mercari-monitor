# -*- mode: python ; coding: utf-8 -*-
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
