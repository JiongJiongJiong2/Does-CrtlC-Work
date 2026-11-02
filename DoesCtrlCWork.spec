# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
import sys

version_resource = runpy.run_path(str(Path(SPECPATH) / 'tools' / 'generate_version.py'))['resource']()
(Path(SPECPATH) / 'version.txt').write_text(version_resource, encoding='utf-8')


# PyWinRT 4 uses real _table.pywinrt files and resolves projected namespaces
# dynamically. Its official hook collects those tables, installed projection
# imports and redistributed component DLLs. Keep that hook, rather than broad
# --collect-all flags or a duplicate private hook. Native Windows system APIs
# come from the OS; these wheels do not ship Windows SDK WinMD files.
WINRT_MODULES = [
    'winrt.windows.devices.bluetooth',
    'winrt.windows.devices.bluetooth.advertisement',
    'winrt.windows.devices.bluetooth.genericattributeprofile',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.storage.streams',
] if sys.platform == 'win32' else []
WINRT_HOOK_DIRS = []
if WINRT_MODULES:
    try:
        from winrt.__pyinstaller import get_hook_dirs
    except ImportError as error:
        raise SystemExit('Install requirements-build.txt before building Windows discovery.') from error
    WINRT_HOOK_DIRS = get_hook_dirs()


# Qt for Python's hooks discover dynamic dependencies conservatively. This
# application is QWidget/QPainter based and deliberately does not ship QML,
# Quick, PDF, SVG, virtual keyboard, or Qt OpenGL APIs.
# QtNetwork and TLS are required for cancellable, opt-in image requests.
EXCLUDED_QT_BINARIES = {
    'PySide6/Qt6OpenGL.dll',
    'PySide6/Qt6Pdf.dll',
    'PySide6/Qt6Qml.dll',
    'PySide6/Qt6QmlMeta.dll',
    'PySide6/Qt6QmlModels.dll',
    'PySide6/Qt6QmlWorkerScript.dll',
    'PySide6/Qt6Quick.dll',
    'PySide6/Qt6Svg.dll',
    'PySide6/Qt6VirtualKeyboard.dll',
    # QWidget/QPainter rendering does not use Qt's bundled software OpenGL
    # fallback. Keep this exclusion covered by the startup and desktop smoke
    # tests because it is a large, optional rendering fallback.
    'PySide6/opengl32sw.dll',
    'PySide6/plugins/generic/qtuiotouchplugin.dll',
    'PySide6/plugins/iconengines/qsvgicon.dll',
    'PySide6/plugins/imageformats/qpdf.dll',
    'PySide6/plugins/imageformats/qsvg.dll',
    'PySide6/plugins/imageformats/qtga.dll',
    'PySide6/plugins/imageformats/qtiff.dll',
    'PySide6/plugins/imageformats/qwbmp.dll',
    'PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
    'PySide6/plugins/platforms/qdirect2d.dll',
    'PySide6/plugins/platforms/qminimal.dll',
    'PySide6/plugins/platforms/qoffscreen.dll',
}
EXCLUDED_QT_DATA_PREFIXES = ('PySide6/translations/',)
# Qt 6.11 uses the unversioned ICU API supplied by supported Windows versions.
# Analysis can instead find Poppler's ICU 78 on the build host's PATH; its
# versioned exports break QtCore loading. Do not bundle that DLL or its sole
# data dependency, so Windows resolves its own ICU implementation.
EXCLUDED_WINDOWS_ICU_BINARIES = {'icuuc.dll', 'icudt78.dll'} if sys.platform == 'win32' else set()


def should_collect_qt_entry(entry):
    destination = entry[0].replace('\\', '/')
    return (destination not in EXCLUDED_QT_BINARIES and
            destination.lower() not in EXCLUDED_WINDOWS_ICU_BINARIES and
            not destination.startswith(EXCLUDED_QT_DATA_PREFIXES))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
    ],
    hiddenimports=WINRT_MODULES + (['winrt._winrt'] if WINRT_MODULES else []),
    hookspath=WINRT_HOOK_DIRS,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtOpenGL',
        'PySide6.QtPdf',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtSvg',
        'PySide6.QtVirtualKeyboard',
    ],
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if should_collect_qt_entry(entry)]
a.datas = [entry for entry in a.datas if should_collect_qt_entry(entry)]
if WINRT_MODULES:
    collected_data = {entry[0].replace('\\', '/') for entry in a.datas}
    missing_tables = [module for module in WINRT_MODULES
                      if module.replace('.', '/') + '/_table.pywinrt' not in collected_data]
    runtime_present = any(entry[0].replace('\\', '/').startswith('winrt/_winrt')
                          and entry[0].lower().endswith('.pyd') for entry in a.binaries)
    if missing_tables or not runtime_present:
        raise SystemExit('Incomplete PyWinRT bundle: verify requirements-build.txt and official hook; '
                         f'missing tables={missing_tables}, runtime present={runtime_present}')
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DoesCtrlCWork',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version.txt',
    icon=['app_icon.ico'],
)
