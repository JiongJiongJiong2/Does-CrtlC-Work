# -*- mode: python ; coding: utf-8 -*-


# Qt for Python's hooks discover dynamic dependencies conservatively. This
# application is QWidget/QPainter based and deliberately does not ship QML,
# Quick, PDF, SVG, virtual keyboard, Qt Network, or Qt OpenGL APIs.
EXCLUDED_QT_BINARIES = {
    'PySide6/Qt6OpenGL.dll',
    'PySide6/Qt6Network.dll',
    'PySide6/QtNetwork.pyd',
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
    'PySide6/plugins/networkinformation/qnetworklistmanager.dll',
    'PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
    'PySide6/plugins/platforms/qdirect2d.dll',
    'PySide6/plugins/platforms/qminimal.dll',
    'PySide6/plugins/platforms/qoffscreen.dll',
    'PySide6/plugins/tls/qcertonlybackend.dll',
    'PySide6/plugins/tls/qopensslbackend.dll',
    'PySide6/plugins/tls/qschannelbackend.dll',
}
EXCLUDED_QT_DATA_PREFIXES = ('PySide6/translations/',)


def should_collect_qt_entry(entry):
    destination = entry[0].replace('\\', '/')
    return (destination not in EXCLUDED_QT_BINARIES and
            not destination.startswith(EXCLUDED_QT_DATA_PREFIXES))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
        ('assets/image_layout/*.ico', 'assets/image_layout'),
        ('assets/image_layout/LICENSE.txt', 'assets/image_layout'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtOpenGL',
        'PySide6.QtNetwork',
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
