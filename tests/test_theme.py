"""Tests for independently configurable tray and feedback colours."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from config import COLORS, IMAGE_STACK
from ui.theme import ThemeController, tray_colors
from ui.tray_menu import TrayMenuPopup
from ui.text_style import TextStyleResolver


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type and value is not None else value

    def setValue(self, key, value):
        self.values[key] = value


def app():
    return QApplication.instance() or QApplication([])


class ThemeOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()

    def tearDown(self):
        controller = ThemeController(self.settings)
        controller.reset_color_overrides()
        controller.set_palette('classic')

    def setUp(self):
        self.settings = MemorySettings()

    def test_independent_colours_are_persisted_and_applied(self):
        controller = ThemeController(self.settings)
        controller.set_color_override('menu', '#ffffff')
        controller.set_color_override('content', '#404040')
        controller.set_color_override('menu_text', '#00aaff')
        controller.set_color_override('content_text', '#ffd000')
        controller.set_color_override('image', '#203040')

        self.assertEqual(tray_colors().surface, '#ffffff')
        self.assertEqual(COLORS['box_bg'][:3], (64, 64, 64))
        self.assertEqual(COLORS['text'], '#ffd000')
        self.assertEqual(tray_colors().text, '#00aaff')
        self.assertEqual(IMAGE_STACK['bg_color'][:3], (32, 48, 64))

        restored = ThemeController(self.settings)
        self.assertEqual(restored.color_overrides['menu'], '#ffffff')
        self.assertEqual(restored.color_overrides['content'], '#404040')
        self.assertEqual(restored.color_overrides['menu_text'], '#00aaff')

    def test_popup_exposes_each_component_as_a_menu_action(self):
        popup = TrayMenuPopup('en')
        self.assertEqual(set(popup._color_actions),
                         {'menu', 'menu_text', 'content', 'content_text', 'image'})
        self.assertIn('Component colours', popup._color_menu.title())

    def test_popup_exposes_separate_english_and_chinese_font_actions(self):
        popup = TrayMenuPopup('en')
        popup.set_content_fonts('Consolas', 'Microsoft YaHei UI')

        self.assertEqual(set(popup._font_actions), {'latin', 'cjk'})
        self.assertIn('Consolas', popup._font_actions['latin'].text())
        self.assertIn('Microsoft YaHei UI', popup._font_actions['cjk'].text())

    def test_font_dialog_result_applies_selected_family(self):
        popup = TrayMenuPopup('en')
        received = []
        popup.font_target_changed.connect(lambda target, family: received.append((target, family)))
        with patch('PySide6.QtWidgets.QFontDialog.getFont',
                   return_value=(True, QFont('Consolas'))):
            popup._choose_content_font('latin')

        self.assertEqual(received, [('latin', 'Consolas')])

    def test_content_font_override_rebuilds_cached_text_style(self):
        TextStyleResolver.set_content_fonts('Consolas', 'Microsoft YaHei UI')
        self.assertEqual(TextStyleResolver.resolve('English').font.families()[0], 'Consolas')
        self.assertEqual(TextStyleResolver.resolve('中文').font.families()[0], 'Microsoft YaHei UI')
        TextStyleResolver.set_content_fonts()

    def test_legacy_text_override_migrates_to_both_text_surfaces(self):
        self.settings.setValue('color_overrides', '{"text": "#123456"}')
        controller = ThemeController(self.settings)

        self.assertEqual(controller.color_overrides['menu_text'], '#123456')
        self.assertEqual(controller.color_overrides['content_text'], '#123456')
        self.assertEqual(tray_colors().text, '#123456')
        self.assertEqual(COLORS['text'], '#123456')
