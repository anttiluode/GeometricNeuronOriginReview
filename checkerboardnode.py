"""
CheckerboardNode

Generates a simple checkerboard texture.
"""

import numpy as np
import cv2

# --- Magic import block ---
import __main__
BaseNode = __main__.BaseNode
QtGui = __main__.QtGui
# --------------------------

class CheckerboardNode(BaseNode):
    """
    Generates a checkerboard texture.
    """
    NODE_CATEGORY = "Generator"
    NODE_COLOR = QtGui.QColor(200, 200, 200) # Gray

    def __init__(self, size=256):
        super().__init__()
        self.node_title = "Checkerboard"
        
        self.inputs = {
            'square_size': 'signal' # 0-1, size of the squares
        }
        self.outputs = {'image': 'image'}
        
        self.size = int(size)
        self.display_image = np.zeros((self.size, self.size, 3), dtype=np.float32)

    def step(self):
        # 1. Get Controls
        size_in = self.get_blended_input('square_size', 'sum') or 0.1
        square_size = int(5 + size_in * 50) # 5px to 55px
        
        # 2. Generate Grid
        y, x = np.mgrid[0:self.size, 0:self.size]
        
        # 3. Create Checkerboard
        check_pattern = ((x // square_size) + (y // square_size)) % 2
        
        self.display_image = np.stack([check_pattern] * 3, axis=-1).astype(np.float32)
        
    def get_output(self, port_name):
        if port_name == 'image':
            return self.display_image
        return None