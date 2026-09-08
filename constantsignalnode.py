"""
Constant Signal Node - Outputs a fixed, configurable signal value.
Useful for providing stable parameters or triggers.
Place this file in the 'nodes' folder
"""

import numpy as np
from PyQt6 import QtGui
from PIL import Image, ImageDraw, ImageFont
import os

import __main__
BaseNode = __main__.BaseNode
PA_INSTANCE = getattr(__main__, "PA_INSTANCE", None)

class ConstantSignalNode(BaseNode):
    NODE_CATEGORY = "Source"
    NODE_COLOR = QtGui.QColor(40, 120, 80) # Source Green
    
    def __init__(self, value=1.0):
        super().__init__()
        self.node_title = "Constant Signal"
        self.outputs = {'signal': 'signal'}
        self.value = float(value)
        
        # Try to load a font for display
        try:
            self.font = ImageFont.load_default(size=14)
        except IOError:
            self.font = None

    def step(self):
        # Do nothing, the value is constant
        pass
        
    def get_output(self, port_name):
        if port_name == 'signal':
            return self.value
        return None
        
    def get_display_image(self):
        w, h = 64, 32  # Small and wide
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img_pil = Image.fromarray(img)
        draw = ImageDraw.Draw(img_pil)
        
        text = f"{self.value:.2f}"
        text_color = (200, 200, 200)
        
        try:
            bbox = draw.textbbox((0, 0), text, font=self.font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (w - text_w) / 2
            y = (h - text_h) / 2
        except Exception:
            x, y = 5, 5 # Fallback
            
        draw.text((x, y), text, fill=text_color, font=self.font)
        
        img_final = np.array(img_pil)
        img_final = np.ascontiguousarray(img_final)
        return QtGui.QImage(img_final.data, w, h, 3*w, QtGui.QImage.Format.Format_RGB888)

    def get_config_options(self):
        return [
            ("Value", "value", self.value, None)
        ]