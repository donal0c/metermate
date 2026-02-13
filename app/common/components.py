"""Reusable UI components for Energy Insight.

Provides HTML-rendering helpers for bill fields, anomaly cards,
and other repeated UI patterns used across pages.
"""
import streamlit as st
from common.theme import (
    CARD_BG,
    TEXT_BODY,
    TEXT_MUTED,
    TEXT_DIM,
    FONT_MONO,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ALERT,
    TEXT_PRIMARY,
)


def fmt_value(value, prefix="", suffix="", fmt_spec=None):
    """Format a value for display, returning a dash if None."""
    if value is None:
        return "\u2014"
    if fmt_spec:
        return f"{prefix}{value:{fmt_spec}}{suffix}"
    return f"{prefix}{value}{suffix}"


def field_html(label: str, value, *, warn: bool = False,
               edited: bool = False, original: str | None = None) -> str:
    """Render a single key-value field as styled HTML.

    Args:
        label: Field label (e.g. "Supplier").
        value: Display value (string). None renders as a dash.
        warn: If True and value is not None, show a warning indicator.
        edited: If True, show blue "manually corrected" indicator.
        original: Original extracted value (shown as tooltip when edited).
    """
    if edited and value is not None:
        tooltip = f' title="Originally extracted: {original}"' if original else ''
        return (
            f'<div data-testid="edited-field" style="border-left: 3px solid #3b82f6; '
            f'padding-left: 0.5rem; margin-bottom: 0.4rem;"{tooltip}>'
            f'<span style="color: {TEXT_MUTED}; font-size: 0.8rem;">{label}</span><br>'
            f'<span style="color: #3b82f6; font-family: {FONT_MONO}; '
            f'font-size: 0.95rem;">{value}</span>'
            f'<span style="color: #3b82f6; font-size: 0.7rem; margin-left: 0.3rem;">'
            f'manually corrected</span></div>'
        )
    if warn and value is not None:
        return (
            f'<div style="border-left: 3px solid {SEVERITY_WARNING}; padding-left: 0.5rem; '
            f'margin-bottom: 0.4rem;">'
            f'<span style="color: {TEXT_MUTED}; font-size: 0.8rem;">{label}</span><br>'
            f'<span style="color: {TEXT_BODY}; font-family: {FONT_MONO}; '
            f'font-size: 0.95rem;">\u26a0\ufe0f {value}</span></div>'
        )
    display_val = value if value is not None else "\u2014"
    color = TEXT_DIM if value is None else TEXT_BODY
    return (
        f'<div style="margin-bottom: 0.4rem;">'
        f'<span style="color: {TEXT_MUTED}; font-size: 0.8rem;">{label}</span><br>'
        f'<span style="color: {color}; font-family: {FONT_MONO}; '
        f'font-size: 0.95rem;">{display_val}</span></div>'
    )


def render_anomaly_cards(anomalies: list):
    """Render anomaly cards with severity-colored borders and cost display."""
    severity_order = {'alert': 0, 'warning': 1, 'info': 2}
    severity_colors = {
        'info': SEVERITY_INFO,
        'warning': SEVERITY_WARNING,
        'alert': SEVERITY_ALERT,
    }
    severity_icons = {'info': '\u2139\ufe0f', 'warning': '\u26a0\ufe0f', 'alert': '\U0001f6a8'}

    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: severity_order.get(a.get('severity', 'info'), 3)
    )

    for a in sorted_anomalies:
        sev = a.get('severity', 'info')
        color = severity_colors.get(sev, SEVERITY_INFO)
        icon = severity_icons.get(sev, '\u2022')
        cost = a.get('annual_cost_eur', 0)
        recommendation = a.get('recommendation', '')

        cost_html = ''
        if cost > 1:
            cost_html = (
                '<div style="text-align: right; padding-left: 1.5rem; min-width: 100px;">'
                f'<div style="color: {color}; font-family: {FONT_MONO}; '
                f'font-size: 1.3rem; font-weight: 700;">\u20ac{cost:,.0f}</div>'
                '<div style="color: #64748b; font-size: 0.75rem;">per year</div>'
                '</div>'
            )

        rec_html = ''
        if recommendation:
            rec_html = (
                f'<div style="color: {TEXT_SECONDARY}; font-size: 0.85rem; font-style: italic;">'
                f'{recommendation}</div>'
            )

        card_html = (
            f'<div style="padding: 1rem 1.2rem; border-left: 4px solid {color}; '
            f'background: {CARD_BG}; border-radius: 0 8px 8px 0; margin-bottom: 0.75rem;">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div style="flex: 1;">'
            f'<div style="color: {TEXT_PRIMARY}; font-weight: 600; font-size: 1rem; margin-bottom: 0.3rem;">'
            f'{icon} {a["title"]}</div>'
            f'<div style="color: {TEXT_MUTED}; font-size: 0.9rem; margin-bottom: 0.5rem;">'
            f'{a["description"]}</div>'
            f'{rec_html}'
            f'</div>{cost_html}</div></div>'
        )

        st.markdown(card_html, unsafe_allow_html=True)


# Re-export TEXT_SECONDARY for the card template (avoids direct theme import in callers)
from common.theme import TEXT_SECONDARY  # noqa: E402
