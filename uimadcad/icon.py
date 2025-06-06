import importlib, re

from madcad.qt import Qt, QIcon, QIconEngine, QColor, QApplication, QPalette, QPixmap, QPainter

from . import settings, resourcedir
from . import utils

# import QtSvg, but using the same qt wrapper as pymadcad
QtSvg = importlib.import_module(Qt.__module__.split('.')[0] + '.QtSvg')


def icon_from_theme(name):
    ''' load a theme icon from the project icon folder '''
    return QIcon(QThemeIconEngine(name))

class QThemeIconEngine(QIconEngine):
    ''' icon renderer following the svg symbolic icon specifications from freedesktop.org '''

    _pattern = re.compile('<style\s(.*?)</style>', re.DOTALL)
    _cache = {}
    
    def __init__(self, name:str):
        super().__init__()
        self.name = name

    def clone(self):
        return QThemeIconEngine(self.name)

    def paint(self, painter, rect, mode, state):
        painter.drawPixmap(rect.topLeft(), self.pixmap(rect.size(), mode, state))
        
    def pixmap(self, size, mode, state):
        # cache svg rendering to fasten painting
        key = (self.name, utils.qsize_to_vec(size), mode)
        if key not in self._cache:
            self._cache[key] = self._pixmap(size, mode, state)
        return self._cache[key]
    
    def _pixmap(self, size, mode, state):
        ''' compute pixmap, only called when cache is empty '''
        # cache svg source to avoid file access
        if self.name not in self._cache:
            self._cache[self.name] = self._source()
        source = self._cache[self.name]
        
        # apply theme color
        palette = QApplication.palette()
        if mode == QIcon.Mode.Disabled:
            highlight = qcolor_to_hex(palette.color(QPalette.ColorRole.Midlight))
            text = qcolor_to_hex(palette.color(QPalette.ColorRole.Dark))
        else:
            highlight = qcolor_to_hex(palette.color(QPalette.ColorRole.Highlight))
            text = qcolor_to_hex(palette.color(QPalette.ColorRole.Text))
        style = '''
            <style id="current-color-scheme" type="text/css">
                .ColorScheme-Highlight {{ color:{}; }}
                .ColorScheme-Text {{ color:{}; }}
                .ColorScheme-NegativeText {{ color:{}; }}
            </style>
            '''.format(
                highlight,
                text,
                text,
            )
        source = self._pattern.sub(style, source)
        # render target
        renderer = QtSvg.QSvgRenderer(source.encode("utf-8"))
        
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        return pixmap
        
    def _source(self):
        ''' icon svg source code, only called when cache is empty '''
        # load icon file
        return open(f'{resourcedir}/icons/{self.name}.svg').read()


def qcolor_to_hex(color:QColor) -> str:
    ''' convert a color to hex (web) representation '''
    return '#{:2x}{:2x}{:2x}'.format(color.red(), color.green(), color.blue())
