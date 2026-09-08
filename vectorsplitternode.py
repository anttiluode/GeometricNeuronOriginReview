"""
Vector Splitter Node - ENHANCED (v2)
------------------------------------
Splits a high-dimensional vector (Spectrum) into individual signals.
Crucial for connecting:
- VAE Latent Space -> Eigenmode Generator
- Inverse Scanner DNA -> Eigenmode Generator
- Hyper-Signal -> Anything

Features:
- Visual Bar Graph of the vector.
- Dynamic scaling.
- Robust input handling.
"""

import numpy as np
import cv2
import __main__
BaseNode = __main__.BaseNode
QtGui = __main__.QtGui

class VectorSplitterNode(BaseNode):
    NODE_CATEGORY = "Utility"
    NODE_COLOR = QtGui.QColor(150, 150, 150) # Gray
    
    def __init__(self, num_outputs=16, scale=1.0):
        super().__init__()
        self.node_title = "Vector Splitter"
        
        self.num_outputs = int(num_outputs)
        self.scale = float(scale)
        
        self.inputs = {
            'spectrum_in': 'spectrum', # The Vector (DNA or Latent)
            'scale_mod': 'signal'      # Dynamic scaling (optional)
        }
        
        # Create N outputs
        self.outputs = {}
        for i in range(self.num_outputs):
            self.outputs[f'out_{i}'] = 'signal'
        
        # Internal state
        self.current_vector = np.zeros(self.num_outputs, dtype=np.float32)
        self.display_img = np.zeros((100, 200, 3), dtype=np.uint8)

    def step(self):
        # 1. Get Input
        vector = self.get_blended_input('spectrum_in', 'first')
        mod = self.get_blended_input('scale_mod', 'sum')
        
        # Determine final scale
        current_scale = self.scale
        if mod is not None:
            current_scale *= (1.0 + mod)
            
        if vector is None:
            self.current_vector[:] = 0
            return

        # 2. Process Vector
        # Handle different input types (list, array)
        if isinstance(vector, list):
            vector = np.array(vector, dtype=np.float32)
            
        # Resize if mismatch
        if len(vector) != self.num_outputs:
            # If input is smaller, pad with zeros
            # If input is larger, truncate
            new_vec = np.zeros(self.num_outputs, dtype=np.float32)
            limit = min(len(vector), self.num_outputs)
            new_vec[:limit] = vector[:limit]
            vector = new_vec
            
        # Apply scale
        self.current_vector = vector * current_scale
        
        # 3. Set Outputs
        for i in range(self.num_outputs):
            # Store each channel so get_output can find it
            setattr(self, f'out_{i}_val',float(self.current_vector[i]))

        # 4. Visualization (The DNA Barcode)
        w, h = 200, 100
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        if self.num_outputs > 0:
            bar_w = w / self.num_outputs
            max_val = np.max(np.abs(self.current_vector)) + 1e-9
            
            for i in range(self.num_outputs):
                val = self.current_vector[i]
                
                # Normalize height relative to max in this frame (auto-gain view)
                # or relative to fixed 1.0? Let's use fixed 1.0 for stability
                norm_h = np.clip(val, -1, 1) 
                
                # Map -1..1 to pixels
                px_h = int(abs(norm_h) * (h/2 - 5))
                x = int(i * bar_w)
                
                # Center line is h/2
                y_base = h // 2
                
                if norm_h > 0:
                    # Green bars up
                    cv2.rectangle(img, (x, y_base - px_h), (int(x + bar_w - 1), y_base), (0, 255, 0), -1)
                else:
                    # Red bars down
                    cv2.rectangle(img, (x, y_base), (int(x + bar_w - 1), y_base + px_h), (0, 0, 255), -1)
                    
                # Grid lines
                if i % 4 == 0:
                    cv2.line(img, (x, 0), (x, h), (50, 50, 50), 1)

        self.display_img = img

    def get_output(self, port_name):
        # Dynamic retrieval of outputs out_0, out_1...
        if port_name.startswith('out_'):
            if hasattr(self, f'{port_name}_val'):
                return getattr(self, f'{port_name}_val')
            return 0.0
        return None

    def get_display_image(self):
        return QtGui.QImage(self.display_img.data, 200, 100, 600, QtGui.QImage.Format.Format_RGB888)
        
    def get_config_options(self):
        return [
            ("Num Outputs", "num_outputs", self.num_outputs, None),
            ("Scale", "scale", self.scale, None)
        ]