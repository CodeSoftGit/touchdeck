from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF


def easing_curve() -> QEasingCurve:
    """Shared easing used for all UI animations."""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.42, 0.0), QPointF(0.58, 1.0), QPointF(1.0, 1.0)
    )
    return curve
