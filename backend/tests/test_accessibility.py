"""Automated Accessibility (a11y) & WCAG 2.1 Compliance Tests."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_HTML = ROOT / "frontend" / "public" / "index.html"
STYLE_CSS = ROOT / "frontend" / "public" / "style.css"


class TestAccessibilityCompliance:
    """Validate WCAG 2.1 AA guidelines in HTML & CSS."""

    def setup_method(self):
        assert INDEX_HTML.exists(), "index.html must exist"
        self.html = INDEX_HTML.read_text(encoding="utf-8")
        self.css = STYLE_CSS.read_text(encoding="utf-8") if STYLE_CSS.exists() else ""

    def test_html_lang_attribute_present(self):
        """1. HTML tag specifies a valid language (WCAG 3.1.1)."""
        match = re.search(r'<html[^>]*lang=["\']([a-zA-Z\-]+)["\']', self.html, re.IGNORECASE)
        assert match is not None, "HTML tag is missing the 'lang' attribute"
        assert match.group(1).lower() in ("en", "en-us", "en-gb")

    def test_viewport_meta_scalable(self):
        """2. Viewport allows zoom and responsive scaling (WCAG 1.4.4)."""
        assert 'name="viewport"' in self.html.lower()
        assert "user-scalable=no" not in self.html.lower(), "Avoid user-scalable=no for accessibility"

    def test_skip_to_main_content_link_exists(self):
        """3. Bypass blocks: Skip link present at top of body (WCAG 2.4.1)."""
        assert 'class="skip-link"' in self.html or 'skip to main' in self.html.lower()

    def test_aria_live_regions_present_for_dynamic_content(self):
        """4. Dynamic updates/toasts have aria-live regions (WCAG 4.1.3)."""
        assert 'aria-live="polite"' in self.html or 'aria-live="assertive"' in self.html

    def test_navigation_has_aria_role_and_label(self):
        """5. Nav elements have role and landmark labels (WCAG 1.3.1)."""
        assert '<nav' in self.html.lower()
        assert 'aria-label=' in self.html or 'role="navigation"' in self.html

    def test_modal_has_dialog_role_and_modal_state(self):
        """6. Modals declare role='dialog' and aria-modal='true' (WCAG 4.1.2)."""
        assert 'role="dialog"' in self.html
        assert 'aria-modal="true"' in self.html

    def test_interactive_buttons_have_labels(self):
        """7. Buttons with icons declare aria-label or accessible text (WCAG 1.1.1)."""
        # All button tags should have aria-label or visible inner text
        button_tags = re.findall(r'<button([^>]*)>(.*?)</button>', self.html, re.DOTALL | re.IGNORECASE)
        for attrs, inner_text in button_tags:
            clean_text = re.sub(r'<[^>]+>', '', inner_text).strip()
            has_aria_label = 'aria-label' in attrs or 'title' in attrs
            assert len(clean_text) > 0 or has_aria_label, f"Button lacks accessible name: {attrs}"

    def test_css_has_focus_visible_styles(self):
        """8. CSS defines high-visibility focus states (WCAG 2.4.7)."""
        assert ":focus-visible" in self.css or ":focus" in self.css

    def test_css_respects_reduced_motion(self):
        """9. CSS includes prefers-reduced-motion media query (WCAG 2.3.3)."""
        assert "prefers-reduced-motion" in self.css

    def test_css_screen_reader_utility_class(self):
        """10. CSS provides .sr-only / screen-reader class."""
        assert ".sr-only" in self.css or "skip-link" in self.css
