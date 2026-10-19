"""Shared form controls used across Studio panels."""
from claynext.gui.components.controls.fields import SearchField, SelectField
from claynext.gui.components.controls.scrub_spin import ScrubSpinBox
from claynext.gui.components.controls.section import CollapsibleSection
from claynext.gui.components.controls.spinner import Spinner
from claynext.gui.components.controls.tabs import SegmentTabs

__all__ = [
    "CollapsibleSection",
    "ScrubSpinBox",
    "SearchField",
    "SegmentTabs",
    "SelectField",
    "Spinner",
]
