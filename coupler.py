"""
Homeostatic Coupler Node (The Thermostat)
------------------------------------------
The missing piece for sustained complex dynamics in feedback loops.

Sits between any two nodes in a feedback path. Instead of raw
signal passthrough (which explodes or collapses), it applies:

1. SETPOINT: A target value the system tries to maintain
2. NONLINEARITY: Sigmoid/tanh that prevents runaway
3. INTEGRAL CONTROL: Slow drift toward setpoint (anti-windup)
4. DEAD ZONE: Region around setpoint where signal passes through
   unmodified — allows local dynamics without global correction

The key insight: biological homeostasis doesn't clamp signals
to fixed values. It creates a BASIN OF ATTRACTION around a
setpoint, where the system is free to fluctuate but gets pushed
back if it drifts too far. That's what this does.

Use cases:
- Between Observer free_energy and Drum inhibition (your homeo system)
- Between two EigenToImage nodes in a feedback loop
- Between any output and any input that forms a cycle

Three operating modes:
- REGULATE: Classic thermostat — push signal toward setpoint
- EDGE_OF_CHAOS: Maximize variance — push signal AWAY from 
  equilibrium but prevent explosion (most interesting regime)
- PASSTHROUGH: Just apply the nonlinearity, no regulation
"""

import numpy as np
import cv2
from collections import deque

import __main__
BaseNode = __main__.BaseNode
QtGui = __main__.QtGui


class HomeostaticCouplerNode(BaseNode):
    NODE_CATEGORY = "Control"
    NODE_COLOR = QtGui.QColor(220, 180, 40)  # Gold — the governor
    
    def __init__(self):
        super().__init__()
        self.node_title = "Homeostatic Coupler"
        
        self.inputs = {
            'signal_in': 'signal',       # Main signal to regulate
            'image_in': 'image',         # OR: image passthrough with gain control
            'setpoint_mod': 'signal',    # External setpoint adjustment
            'gain_mod': 'signal'         # External gain adjustment
        }
        
        self.outputs = {
            'signal_out': 'signal',      # Regulated signal
            'image_out': 'image',        # Regulated image (gain-controlled)
            'error': 'signal',           # Distance from setpoint
            'regime': 'signal',          # Current operating regime indicator
            'history_plot': 'image'      # Visual: signal history + setpoint
        }
        
        # === Core Parameters ===
        self.setpoint = 0.5          # Target value
        self.gain = 1.0              # Output gain (post-nonlinearity)
        self.sharpness = 3.0         # Sigmoid steepness (higher = harder clamp)
        self.dead_zone = 0.1         # Region around setpoint with no correction
        
        # Operating mode
        self.mode = 'regulate'       # 'regulate', 'edge_of_chaos', 'passthrough'
        
        # Integral controller (slow drift correction)
        self.integral_gain = 0.01    # How fast the integral winds up
        self.integral_state = 0.0    # Accumulated error
        self.integral_limit = 0.5    # Anti-windup clamp
        
        # Edge-of-chaos parameters
        self.target_variance = 0.1   # Desired signal variance
        self.variance_window = 50    # Window for variance estimation
        
        # State tracking
        self.current_value = 0.0
        self.output_value = 0.0
        self.error_value = 0.0
        self.regime_value = 0.0      # -1=suppressing, 0=dead zone, +1=exciting
        
        # History for display and variance calc
        self.history = deque(maxlen=200)
        self.output_history = deque(maxlen=200)
        
        # Image regulation state
        self.image_gain_state = 1.0
        
        # Display
        self.plot_img = np.zeros((128, 256, 3), dtype=np.uint8)
    
    def _sigmoid(self, x, center, sharpness):
        """Shifted sigmoid: output range (-1, 1) centered on 'center'"""
        z = (x - center) * sharpness
        return 2.0 / (1.0 + np.exp(-z)) - 1.0
    
    def _regulate(self, value, setpoint):
        """
        Classic homeostatic regulation.
        Push signal toward setpoint, allow free movement in dead zone.
        """
        error = value - setpoint
        
        # Dead zone: no correction if close enough
        if abs(error) < self.dead_zone:
            self.regime_value = 0.0
            # Pass through with just the nonlinearity
            output = value
        else:
            # Proportional correction
            correction = self._sigmoid(error, 0.0, self.sharpness)
            
            # Integral correction (slow drift)
            self.integral_state += error * self.integral_gain
            self.integral_state = np.clip(self.integral_state, 
                                          -self.integral_limit, 
                                          self.integral_limit)
            
            # Output: setpoint + bounded deviation + integral
            output = setpoint + correction / self.sharpness - self.integral_state
            
            self.regime_value = -np.sign(error)  # -1 suppressing, +1 boosting
        
        self.error_value = error
        return output * self.gain
    
    def _edge_of_chaos(self, value, setpoint):
        """
        The interesting mode. Instead of pushing toward a fixed value,
        this tries to maintain a target VARIANCE. If the signal is too
        stable, it amplifies deviations. If too wild, it dampens them.
        
        This finds the edge between order and chaos.
        """
        # Estimate current variance from recent history
        if len(self.history) > 10:
            recent = np.array(list(self.history)[-self.variance_window:])
            current_var = np.var(recent)
        else:
            current_var = 0.0
        
        # Error in variance space
        var_error = current_var - self.target_variance
        
        if var_error > 0:
            # Too chaotic — dampen
            # Apply sigmoid compression
            error = value - setpoint
            dampened = setpoint + self._sigmoid(error, 0.0, self.sharpness) / self.sharpness
            output = dampened
            self.regime_value = -1.0
        else:
            # Too orderly — amplify deviations from setpoint
            error = value - setpoint
            amplified = setpoint + error * (1.0 + abs(var_error) * 10.0)
            # But still clamp to prevent explosion
            output = setpoint + np.tanh((amplified - setpoint) * 2.0)
            self.regime_value = 1.0
        
        self.error_value = var_error
        
        # Slow integral drift of setpoint toward mean (adaptive setpoint)
        if len(self.history) > 20:
            mean_val = np.mean(list(self.history)[-50:])
            self.integral_state = self.integral_state * 0.99 + mean_val * 0.01
        
        return output * self.gain
    
    def _passthrough(self, value):
        """Just apply nonlinearity and gain, no regulation"""
        output = np.tanh(value * self.sharpness) / self.sharpness
        self.error_value = 0.0
        self.regime_value = 0.0
        return output * self.gain
    
    def step(self):
        # Get signal input
        sig_in = self.get_blended_input('signal_in', 'sum')
        sp_mod = self.get_blended_input('setpoint_mod', 'sum')
        gain_mod = self.get_blended_input('gain_mod', 'sum')
        
        # Modulate setpoint and gain from external signals
        effective_setpoint = self.setpoint
        if sp_mod is not None:
            effective_setpoint += float(sp_mod) * 0.1
        
        effective_gain = self.gain
        if gain_mod is not None:
            effective_gain *= (1.0 + float(gain_mod) * 0.5)
        
        # Process signal
        if sig_in is not None:
            value = float(sig_in)
            self.current_value = value
            self.history.append(value)
            
            # Apply selected mode
            if self.mode == 'regulate':
                self.output_value = self._regulate(value, effective_setpoint)
            elif self.mode == 'edge_of_chaos':
                self.output_value = self._edge_of_chaos(value, effective_setpoint)
            else:  # passthrough
                self.output_value = self._passthrough(value)
            
            self.output_history.append(self.output_value)
        
        # Process image input (if connected)
        img_in = self.get_blended_input('image_in', 'first')
        if img_in is not None:
            # Use the signal regulation to control image gain
            # If signal is being suppressed, dim the image
            # If being boosted, brighten it
            target_gain = 1.0 + self.regime_value * 0.3
            self.image_gain_state = 0.95 * self.image_gain_state + 0.05 * target_gain
        
        # Update display
        self._render_plot()
    
    def _render_plot(self):
        """Draw signal history with setpoint and dead zone"""
        h, w = 128, 256
        self.plot_img = np.zeros((h, w, 3), dtype=np.uint8)
        
        if len(self.history) < 2:
            return
        
        hist = np.array(list(self.history))
        out_hist = np.array(list(self.output_history))
        
        # Auto-range
        all_vals = np.concatenate([hist, out_hist]) if len(out_hist) > 0 else hist
        vmin = np.min(all_vals) - 0.1
        vmax = np.max(all_vals) + 0.1
        if vmax - vmin < 0.01:
            vmax = vmin + 1.0
        
        def val_to_y(v):
            return int(h - 1 - (v - vmin) / (vmax - vmin) * (h - 1))
        
        # Draw dead zone band
        sp_y = val_to_y(self.setpoint)
        dz_top = val_to_y(self.setpoint + self.dead_zone)
        dz_bot = val_to_y(self.setpoint - self.dead_zone)
        cv2.rectangle(self.plot_img, (0, dz_top), (w, dz_bot), (30, 40, 30), -1)
        
        # Draw setpoint line
        cv2.line(self.plot_img, (0, sp_y), (w, sp_y), (0, 100, 0), 1)
        
        # Draw input history (cyan)
        for i in range(1, len(hist)):
            x0 = int((i - 1) / len(hist) * w)
            x1 = int(i / len(hist) * w)
            y0 = val_to_y(hist[i - 1])
            y1 = val_to_y(hist[i])
            cv2.line(self.plot_img, (x0, y0), (x1, y1), (200, 200, 0), 1)
        
        # Draw output history (green)
        for i in range(1, len(out_hist)):
            x0 = int((i - 1) / len(out_hist) * w)
            x1 = int(i / len(out_hist) * w)
            y0 = val_to_y(out_hist[i - 1])
            y1 = val_to_y(out_hist[i])
            cv2.line(self.plot_img, (x0, y0), (x1, y1), (0, 255, 0), 1)
        
        # Regime indicator
        if self.regime_value > 0.5:
            color = (0, 255, 0)
            label = "EXCITING"
        elif self.regime_value < -0.5:
            color = (0, 0, 255)
            label = "DAMPING"
        else:
            color = (128, 128, 128)
            label = "NEUTRAL"
        
        cv2.circle(self.plot_img, (w - 15, 15), 8, color, -1)
        
        # Labels
        mode_label = self.mode.upper()
        cv2.putText(self.plot_img, mode_label, (4, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        cv2.putText(self.plot_img, f"sp={self.setpoint:.2f}", (4, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 100, 0), 1)
        cv2.putText(self.plot_img, f"err={self.error_value:.3f}", (4, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 0), 1)
        cv2.putText(self.plot_img, label, (w - 80, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
    
    def get_output(self, port_name):
        if port_name == 'signal_out':
            return self.output_value
        elif port_name == 'image_out':
            img_in = self.get_blended_input('image_in', 'first')
            if img_in is not None:
                return np.clip(img_in * self.image_gain_state, 0, 1)
            return None
        elif port_name == 'error':
            return self.error_value
        elif port_name == 'regime':
            return self.regime_value
        elif port_name == 'history_plot':
            return self.plot_img
        return None
    
    def get_display_image(self):
        display = self.plot_img.copy()
        h, w = display.shape[:2]
        return QtGui.QImage(display.data, w, h, w * 3,
                           QtGui.QImage.Format.Format_RGB888)
    
    def get_config_options(self):
        return [
            ("Mode", "mode", self.mode, 
             [("Regulate", "regulate"), 
              ("Edge of Chaos", "edge_of_chaos"), 
              ("Passthrough", "passthrough")]),
            ("Setpoint", "setpoint", self.setpoint, "float"),
            ("Gain", "gain", self.gain, "float"),
            ("Sharpness", "sharpness", self.sharpness, "float"),
            ("Dead Zone", "dead_zone", self.dead_zone, "float"),
            ("Integral Gain", "integral_gain", self.integral_gain, "float"),
            ("Integral Limit", "integral_limit", self.integral_limit, "float"),
            ("Target Variance", "target_variance", self.target_variance, "float"),
        ]
    
    def set_config_options(self, options):
        if "mode" in options:
            self.mode = str(options["mode"])
        if "setpoint" in options:
            self.setpoint = float(options["setpoint"])
        if "gain" in options:
            self.gain = float(options["gain"])
        if "sharpness" in options:
            self.sharpness = float(options["sharpness"])
        if "dead_zone" in options:
            self.dead_zone = float(options["dead_zone"])
        if "integral_gain" in options:
            self.integral_gain = float(options["integral_gain"])
        if "integral_limit" in options:
            self.integral_limit = float(options["integral_limit"])
        if "target_variance" in options:
            self.target_variance = float(options["target_variance"])