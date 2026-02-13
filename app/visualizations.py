"""
Visualization functions for energy consumption data.

All charts use Plotly for interactive visualizations with a cohesive dark theme.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Color scheme - Cork Energy Consultancy branded (green-focused)
COLORS = {
    'primary': '#4ade80',      # Green accent
    'secondary': '#f59e0b',    # Amber
    'night': '#3b82f6',        # Blue
    'day': '#f59e0b',          # Amber
    'peak': '#ef4444',         # Red
    'export': '#22c55e',       # Green (solar export)
    'import': '#4ade80',       # Green (grid import)
    'grid': '#2d4a40',         # Grid lines
    'text': '#94a3b8',         # Text
    'text_primary': '#f1f5f9', # Primary text
    'bg': '#0f1a17',           # Background
    'severity_info': '#3b82f6',
    'severity_warning': '#f59e0b',
    'severity_alert': '#ef4444',
}

# Plotly layout template for dark theme
LAYOUT_TEMPLATE = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(
        family='DM Sans, -apple-system, BlinkMacSystemFont, sans-serif',
        color=COLORS['text'],
        size=12
    ),
    title=dict(
        font=dict(
            size=16,
            color=COLORS['text_primary']
        ),
        x=0,
        xanchor='left'
    ),
    xaxis=dict(
        gridcolor=COLORS['grid'],
        linecolor=COLORS['grid'],
        tickfont=dict(color=COLORS['text']),
        title_font=dict(color=COLORS['text'])
    ),
    yaxis=dict(
        gridcolor=COLORS['grid'],
        linecolor=COLORS['grid'],
        tickfont=dict(color=COLORS['text']),
        title_font=dict(color=COLORS['text'])
    ),
    legend=dict(
        bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text'])
    ),
    hoverlabel=dict(
        bgcolor=COLORS['bg'],
        font_size=13,
        font_family='DM Sans'
    ),
    margin=dict(l=0, r=20, t=40, b=0)
)

DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def apply_dark_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent dark theme to a figure."""
    fig.update_layout(**LAYOUT_TEMPLATE)
    return fig


def _apply_anomaly_annotations(fig: go.Figure, chart_name: str, anomalies: list | None):
    """Apply chart annotations from anomaly dicts to a figure.

    Ensures annotations stay within the plot area by setting xanchor/yanchor
    on annotations near chart edges.
    """
    if not anomalies:
        return
    for a in anomalies:
        for annot in a.get('chart_annotations', []):
            if annot.get('chart') != chart_name:
                continue
            annot_type = annot.get('type')
            params = annot.get('params', {})
            if annot_type == 'hline':
                fig.add_hline(**params)
            elif annot_type == 'vrect':
                fig.add_vrect(**params)
            elif annot_type == 'annotation':
                # Default to xanchor='left' to prevent right-edge clipping
                if 'xanchor' not in params:
                    params.setdefault('xanchor', 'left')
                fig.add_annotation(**params)


def create_heatmap(df: pd.DataFrame) -> go.Figure:
    """
    Create a heatmap showing consumption by hour of day and day of week.

    This is the signature visualization - shows patterns at a glance.
    """
    # Aggregate by hour and day of week
    pivot = df.pivot_table(
        values='import_kwh',
        index='hour',
        columns='day_of_week',
        aggfunc='mean'
    )

    # Reorder columns to Monday-Sunday
    pivot = pivot[[col for col in DAY_ORDER if col in pivot.columns]]

    # Custom colorscale - green-based (Cork Energy branding)
    colorscale = [
        [0.0, '#0a1210'],
        [0.2, '#14532d'],
        [0.4, '#166534'],
        [0.6, '#22c55e'],
        [0.8, '#4ade80'],
        [1.0, '#bbf7d0']
    ]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=[f'{h:02d}:00' for h in pivot.index],
        colorscale=colorscale,
        colorbar=dict(
            title=dict(text='Avg kWh', font=dict(color=COLORS['text'])),
            tickfont=dict(color=COLORS['text']),
            bgcolor='rgba(0,0,0,0)'
        ),
        hovertemplate='<b>%{x}</b> at <b>%{y}</b><br>Average: <b>%{z:.3f} kWh</b><extra></extra>'
    ))

    fig.update_layout(
        title='',
        xaxis_title='',
        yaxis_title='',
        yaxis=dict(autorange='reversed', dtick=2),
        height=500,
    )

    return apply_dark_theme(fig)


def create_daily_profile(df: pd.DataFrame, anomalies: list = None) -> go.Figure:
    """
    Create a 24-hour load profile chart showing weekday vs weekend patterns.
    """
    # Calculate hourly averages for weekday and weekend
    weekday_profile = df[~df['is_weekend']].groupby('hour')['import_kwh'].mean() * 2  # Convert to kW
    weekend_profile = df[df['is_weekend']].groupby('hour')['import_kwh'].mean() * 2

    fig = go.Figure()

    # Add shaded areas for tariff periods
    # Night period (23:00-08:00) — label on the 0-8 band to avoid right-edge clipping
    fig.add_vrect(x0=23, x1=24, fillcolor=COLORS['night'], opacity=0.1, line_width=0)
    fig.add_vrect(x0=0, x1=8, fillcolor=COLORS['night'], opacity=0.1, line_width=0,
                  annotation_text="Night", annotation_position="top right",
                  annotation=dict(font_color=COLORS['text'], font_size=10))

    # Peak period (17:00-19:00)
    fig.add_vrect(x0=17, x1=19, fillcolor=COLORS['peak'], opacity=0.15, line_width=0,
                  annotation_text="Peak", annotation_position="top right",
                  annotation=dict(font_color=COLORS['text'], font_size=10))

    # Weekday line with area
    fig.add_trace(go.Scatter(
        x=list(weekday_profile.index),
        y=weekday_profile.values,
        mode='lines',
        name='Weekday',
        line=dict(color=COLORS['primary'], width=3),
        fill='tozeroy',
        fillcolor='rgba(74, 222, 128, 0.15)',
        hovertemplate='<b>%{x}:00</b><br>Weekday avg: <b>%{y:.2f} kW</b><extra></extra>'
    ))

    # Weekend line
    fig.add_trace(go.Scatter(
        x=list(weekend_profile.index),
        y=weekend_profile.values,
        mode='lines',
        name='Weekend',
        line=dict(color=COLORS['secondary'], width=3, dash='dot'),
        hovertemplate='<b>%{x}:00</b><br>Weekend avg: <b>%{y:.2f} kW</b><extra></extra>'
    ))

    fig.update_layout(
        title='',
        xaxis_title='Hour of Day',
        yaxis_title='Average Power (kW)',
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(0, 24, 3)),
            ticktext=[f'{h:02d}:00' for h in range(0, 24, 3)],
            range=[-0.5, 23.5]
        ),
        legend=dict(x=0.02, y=0.98, bgcolor='rgba(0,0,0,0.3)'),
        height=400,
        hovermode='x unified'
    )

    _apply_anomaly_annotations(fig, 'daily_profile', anomalies)
    return apply_dark_theme(fig)


def create_tariff_breakdown(df: pd.DataFrame) -> go.Figure:
    """
    Create a donut chart showing consumption by tariff period.
    """
    tariff_totals = df.groupby('tariff_period')['import_kwh'].sum()

    # Ensure order: Day, Peak, Night
    order = ['Day', 'Peak', 'Night']
    values = [tariff_totals.get(t, 0) for t in order]
    colors = [COLORS['day'], COLORS['peak'], COLORS['night']]

    # Calculate percentages
    total = sum(values)
    percentages = [v / total * 100 for v in values]

    fig = go.Figure(data=[go.Pie(
        labels=order,
        values=values,
        marker=dict(
            colors=colors,
            line=dict(color=COLORS['bg'], width=2)
        ),
        hole=0.55,
        textinfo='percent',
        textfont=dict(size=14, color='white'),
        hovertemplate='<b>%{label}</b><br>%{value:,.0f} kWh (%{percent})<extra></extra>'
    )])

    fig.update_layout(
        title='',
        height=400,
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.15,
            xanchor='center',
            x=0.5
        ),
        annotations=[
            dict(
                text=f'<b>{total:,.0f}</b><br><span style="font-size:12px">kWh</span>',
                x=0.5, y=0.5,
                font_size=20,
                font_color=COLORS['text_primary'],
                showarrow=False
            )
        ]
    )

    return apply_dark_theme(fig)


def create_monthly_trend(df: pd.DataFrame, anomalies: list = None) -> go.Figure:
    """
    Create a bar chart showing monthly consumption trends.
    """
    monthly = df.groupby('year_month').agg({
        'import_kwh': 'sum',
        'export_kwh': 'sum'
    }).reset_index()

    monthly = monthly.sort_values('year_month')

    fig = go.Figure()

    # Import bars
    fig.add_trace(go.Bar(
        x=monthly['year_month'],
        y=monthly['import_kwh'],
        name='Import',
        marker=dict(
            color=COLORS['import'],
            line=dict(width=0)
        ),
        hovertemplate='<b>%{x}</b><br>Import: <b>%{y:,.0f} kWh</b><extra></extra>'
    ))

    # Export bars (if any)
    if monthly['export_kwh'].sum() > 0:
        fig.add_trace(go.Bar(
            x=monthly['year_month'],
            y=monthly['export_kwh'],
            name='Export',
            marker=dict(
                color=COLORS['export'],
                line=dict(width=0)
            ),
            hovertemplate='<b>%{x}</b><br>Export: <b>%{y:,.0f} kWh</b><extra></extra>'
        ))

    fig.update_layout(
        title='',
        xaxis_title='',
        yaxis_title='Energy (kWh)',
        barmode='group',
        height=400,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0
        ),
        bargap=0.3
    )

    _apply_anomaly_annotations(fig, 'monthly_trend', anomalies)
    return apply_dark_theme(fig)


def create_daily_trend(df: pd.DataFrame, last_n_days: int = 30, anomalies: list = None) -> go.Figure:
    """
    Create a line chart showing daily consumption for recent days.
    """
    daily = df.groupby('date').agg({
        'import_kwh': 'sum',
        'export_kwh': 'sum'
    }).reset_index()

    daily = daily.sort_values('date').tail(last_n_days)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily['date'],
        y=daily['import_kwh'],
        mode='lines',
        name='Import',
        line=dict(color=COLORS['import'], width=2),
        fill='tozeroy',
        fillcolor='rgba(74, 222, 128, 0.1)',
        hovertemplate='<b>%{x}</b><br>Import: <b>%{y:.1f} kWh</b><extra></extra>'
    ))

    if daily['export_kwh'].sum() > 0:
        fig.add_trace(go.Scatter(
            x=daily['date'],
            y=daily['export_kwh'],
            mode='lines',
            name='Export',
            line=dict(color=COLORS['export'], width=2),
            hovertemplate='<b>%{x}</b><br>Export: <b>%{y:.1f} kWh</b><extra></extra>'
        ))

    fig.update_layout(
        title=f'',
        xaxis_title='',
        yaxis_title='Energy (kWh)',
        height=350,
        legend=dict(x=0.02, y=0.98),
        hovermode='x unified',
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=7, label="1W", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(step="all", label="All"),
                ],
                bgcolor='rgba(30, 41, 59, 0.8)',
                activecolor='rgba(74, 222, 128, 0.3)',
                font=dict(color='#94a3b8'),
            ),
            rangeslider=dict(visible=True, thickness=0.05),
        ),
    )

    _apply_anomaly_annotations(fig, 'daily_trend', anomalies)
    return apply_dark_theme(fig)


def create_import_export_comparison(df: pd.DataFrame) -> go.Figure:
    """
    Create a chart comparing import vs export by hour (for solar analysis).
    """
    hourly = df.groupby('hour').agg({
        'import_kwh': 'mean',
        'export_kwh': 'mean'
    }).reset_index()

    # Convert to kW
    hourly['import_kw'] = hourly['import_kwh'] * 2
    hourly['export_kw'] = hourly['export_kwh'] * 2

    fig = go.Figure()

    # Import bars (positive)
    fig.add_trace(go.Bar(
        x=hourly['hour'],
        y=hourly['import_kw'],
        name='Import from Grid',
        marker=dict(color=COLORS['import']),
        hovertemplate='<b>%{x}:00</b><br>Import: <b>%{y:.2f} kW</b><extra></extra>'
    ))

    # Export bars (negative for visual effect)
    fig.add_trace(go.Bar(
        x=hourly['hour'],
        y=-hourly['export_kw'],
        name='Export to Grid',
        marker=dict(color=COLORS['export']),
        hovertemplate='<b>%{x}:00</b><br>Export: <b>%{customdata:.2f} kW</b><extra></extra>',
        customdata=hourly['export_kw']
    ))

    # Add zero line
    fig.add_hline(y=0, line_color=COLORS['grid'], line_width=1)

    fig.update_layout(
        title='',
        xaxis_title='Hour of Day',
        yaxis_title='Power (kW)',
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(0, 24, 3)),
            ticktext=[f'{h:02d}:00' for h in range(0, 24, 3)]
        ),
        barmode='relative',
        height=400,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0
        ),
        bargap=0.1
    )

    return apply_dark_theme(fig)


def create_baseload_chart(df: pd.DataFrame, anomalies: list = None) -> go.Figure:
    """
    Create a chart highlighting baseload (minimum consumption per day).
    """
    # Get minimum and average per day
    daily_min = df.groupby('date')['import_kwh'].min() * 2  # Convert to kW
    daily_avg = df.groupby('date')['import_kwh'].mean() * 2

    fig = go.Figure()

    # Average consumption area
    fig.add_trace(go.Scatter(
        x=list(daily_avg.index),
        y=daily_avg.values,
        mode='lines',
        name='Daily Average',
        line=dict(color=COLORS['text'], width=1),
        fill='tozeroy',
        fillcolor='rgba(148, 163, 184, 0.1)',
        hovertemplate='<b>%{x}</b><br>Daily avg: <b>%{y:.2f} kW</b><extra></extra>'
    ))

    # Baseload area
    fig.add_trace(go.Scatter(
        x=list(daily_min.index),
        y=daily_min.values,
        mode='lines',
        name='Baseload (Minimum)',
        line=dict(color=COLORS['peak'], width=2),
        fill='tozeroy',
        fillcolor='rgba(239, 68, 68, 0.2)',
        hovertemplate='<b>%{x}</b><br>Baseload: <b>%{y:.2f} kW</b><extra></extra>'
    ))

    # Average baseload reference line
    avg_baseload = daily_min.mean()
    fig.add_hline(
        y=avg_baseload,
        line_dash='dash',
        line_color=COLORS['secondary'],
        annotation_text=f'Avg: {avg_baseload:.2f} kW',
        annotation_position='right',
        annotation=dict(font_color=COLORS['secondary'])
    )

    fig.update_layout(
        title='',
        xaxis_title='',
        yaxis_title='Power (kW)',
        height=350,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0
        ),
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=7, label="1W", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(step="all", label="All"),
                ],
                bgcolor='rgba(30, 41, 59, 0.8)',
                activecolor='rgba(74, 222, 128, 0.3)',
                font=dict(color='#94a3b8'),
            ),
            rangeslider=dict(visible=True, thickness=0.05),
        ),
    )

    _apply_anomaly_annotations(fig, 'baseload_chart', anomalies)
    return apply_dark_theme(fig)
