"""Headless reproduction of the Perception Lab scheduler for ecg.json.

The archived node files in the repository root are imported UNCHANGED. This module only supplies
what the host would have supplied:

* ``BaseNode`` with the input semantics of perception_lab_hostv10.py (identical in perceptionlab11
  and perceptionlab12): ``pre_step`` clears inputs, ``set_input`` multiplies signal values by
  ``coupling_strength * learned_weight``, and ``get_blended_input('sum')`` returns ``np.sum`` of the
  list.
* ``simulation_step``: (1) pre_step every node, (2) transfer every edge in file order, reading each
  source node's *current* output, (3) step every node in file order. Because all transfers happen
  before any node steps, each edge is a one-tick delay.
* ``load_graph``: a node attribute is restored only if a fresh instance already has it
  (``hasattr``). The coupler's history deque is not saved, and the splitter's ``out_i_val``
  attributes do not exist on a fresh instance, so loading the file is NOT resuming the captured
  moment. ``global_settings['coupling']`` sets coupling_strength = coupling/100.
"""
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


class BaseNode:
    """Copied semantics of BaseNode in perception_lab_hostv10.py (lines 84-160)."""

    def __init__(self):
        self.inputs = {}
        self.outputs = {}
        self.input_data = {}
        self.node_title = "Base Node"

    def pre_step(self):
        self.input_data = {name: [] for name in self.inputs}

    def set_input(self, port_name, value, port_type="signal", coupling=1.0):
        if port_name not in self.input_data:
            return
        if port_type == "signal":
            if isinstance(value, (np.ndarray, list)):
                value = value[0] if len(value) > 0 else 0.0
            try:
                fval = float(value)
                if not np.isfinite(fval):
                    fval = 0.0
            except (ValueError, TypeError):
                fval = 0.0
            self.input_data[port_name].append(fval * coupling)
        else:
            if value is not None:
                self.input_data[port_name].append(value)

    def get_blended_input(self, port_name, blend_mode="sum"):
        values = self.input_data.get(port_name, [])
        if not values:
            return None
        if blend_mode == "sum" and isinstance(values[0], (int, float)):
            result = np.sum(values)
            if not np.isfinite(result):
                return 0.0
            return result
        return values[0]

    def step(self):
        pass

    def get_output(self, port_name):
        return None


def _install_host_stubs():
    main = sys.modules["__main__"]
    qt = types.SimpleNamespace(QColor=lambda *a, **k: None,
                               QImage=type("QImage", (), {"Format": types.SimpleNamespace(Format_RGB888=0),
                                                          "__init__": lambda self, *a, **k: None}))
    main.BaseNode = BaseNode
    main.QtGui = qt
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        pkg = types.ModuleType("PyQt6")
        pkg.QtGui = qt
        sys.modules["PyQt6"] = pkg
        sys.modules["PyQt6.QtGui"] = qt


def _node_classes():
    _install_host_stubs()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import checkerboardnode
    import constantsignalnode
    import coupler
    import imagetovectornode
    import vectorsplitternode
    return {"ConstantSignalNode": constantsignalnode.ConstantSignalNode,
            "HomeostaticCouplerNode": coupler.HomeostaticCouplerNode,
            "CheckerboardNode": checkerboardnode.CheckerboardNode,
            "ImageToVectorNode": imagetovectornode.ImageToVectorNode,
            "VectorSplitterNode": vectorsplitternode.VectorSplitterNode}


PORT_TYPES = {"signal": "signal", "signal_out": "signal", "image": "image", "vector_out": "spectrum"}


def port_type(src_port):
    return "signal" if src_port.startswith("out_") else PORT_TYPES[src_port]


class Graph:
    def __init__(self, path=ROOT / "ecg.json", overrides=None, coupling=None):
        data = json.loads(Path(path).read_text())
        classes = _node_classes()
        self.nodes, self.by_id = [], {}
        for nd in data["nodes"]:
            node = classes[nd["class_name"]]()
            for key, value in nd.get("config", {}).items():
                if hasattr(node, key):                       # v10/v11/v12 rule
                    setattr(node, key, value)
            self.nodes.append(node)
            self.by_id[nd["id"]] = node
        for node_id, attrs in (overrides or {}).items():
            for key, value in attrs.items():
                setattr(self.by_id[node_id], key, value)
        self.edges = [(self.by_id[e["from_node_id"]], e["from_port"], self.by_id[e["to_node_id"]],
                       e["to_port"], e.get("learned_weight", 1.0)) for e in data["edges"]]
        settings = data.get("global_settings", {})
        self.coupling = settings.get("coupling", 70)/100.0 if coupling is None else coupling
        self.const, self.coupler, self.board, self.i2v, self.split = (self.by_id[i] for i in range(5))
        self.tick = 0

    def step(self):
        for node in self.nodes:
            node.pre_step()
        for src, sport, tgt, tport, w in self.edges:
            val = src.get_output(sport)
            if val is not None:
                tgt.set_input(tport, val, port_type(sport), self.coupling*w)
        for node in self.nodes:
            node.step()
        self.tick += 1

    def record(self):
        """Values visible after this tick's node steps."""
        c = self.coupler
        size_in = self.board.get_blended_input("square_size", "sum") or 0.1
        return {"r": float(c.current_value), "o": float(c.output_value), "regime": float(c.regime_value),
                "q": int(5 + size_in*50),
                "split4": [float(self.split.get_output(f"out_{i}")) for i in range(4)]}
