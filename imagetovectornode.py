"""
Image To Vector Node (The Bridge)
---------------------------------
Downsamples a 2D image into a 1D latent vector.
Crucial for connecting Visual/Physics nodes (Images) to Cognitive nodes (Vectors).
"""

import numpy as np
import cv2
import __main__
BaseNode = __main__.BaseNode
QtGui = __main__.QtGui

class ImageToVectorNode(BaseNode):
    NODE_CATEGORY = "Utility"
    NODE_COLOR = QtGui.QColor(120, 120, 120)
    
    def __init__(self, output_dim=256):
        super().__init__()
        self.node_title = "Image -> Vector"
        
        self.inputs = {
            'image_in': 'image'
        }
        
        self.outputs = {
            'vector_out': 'spectrum'
        }
        
        # Default to 256 (16x16 grid)
        self.output_dim = int(output_dim)
        self.vector = np.zeros(self.output_dim, dtype=np.float32)

    def step(self):
        img = self.get_blended_input('image_in', 'first')
        
        if img is None:
            return
            
        # 1. Handle dimensions (RGB to Gray)
        if img.ndim == 3:
            img = np.mean(img, axis=2)
            
        # 2. Calculate target square side
        # We want 'output_dim' pixels total. Sqrt(256) = 16x16 grid.
        side = int(np.ceil(np.sqrt(self.output_dim)))
        
        # 3. Resize (Downsample)
        # This averages the pixels, effectively integrating the field information
        tiny_img = cv2.resize(img, (side, side), interpolation=cv2.INTER_AREA)
        
        # 4. Flatten to Vector
        flat = tiny_img.flatten()
        
        # 5. Trim or Pad to exact dimension
        if len(flat) >= self.output_dim:
            self.vector = flat[:self.output_dim]
        else:
            # Pad with zeros if needed
            self.vector = np.zeros(self.output_dim, dtype=np.float32)
            self.vector[:len(flat)] = flat
            
        # Normalize (0..1)
        max_val = np.max(np.abs(self.vector))
        if max_val > 0:
            self.vector /= max_val

    def get_output(self, port_name):
        if port_name == 'vector_out':
            return self.vector
        return None
        
    def get_display_image(self):
        # --- FIX: VISUALIZATION ---
        # Instead of a barcode (which breaks at high dims), 
        # we reshape the vector back into a square grid for display.
        
        # 1. Determine Grid Size
        side = int(np.ceil(np.sqrt(self.output_dim)))
        
        # 2. Reshape Vector to Grid
        # Pad vector to match square size if needed
        total_pixels = side * side
        display_data = np.zeros(total_pixels, dtype=np.float32)
        
        # Copy vector data
        n = min(len(self.vector), total_pixels)
        display_data[:n] = self.vector[:n]
        
        # Reshape to 2D
        grid_img = display_data.reshape((side, side))
        
        # 3. Color Map (Viridis style for data visibility)
        img_u8 = (np.clip(grid_img, 0, 1) * 255).astype(np.uint8)
        img_color = cv2.applyColorMap(img_u8, cv2.COLORMAP_OCEAN)
        
        # 4. Resize for UI visibility (Make it big enough to see)
        img_final = cv2.resize(img_color, (128, 128), interpolation=cv2.INTER_NEAREST)
        
        return QtGui.QImage(img_final.data, 128, 128, 128*3, QtGui.QImage.Format.Format_RGB888)

    def get_config_options(self):
        return [
            ("Vector Size", "output_dim", self.output_dim, None)
        ]
        
    def set_config_options(self, options):
        if "output_dim" in options:
            self.output_dim = int(options["output_dim"])
            self.vector = np.zeros(self.output_dim, dtype=np.float32)