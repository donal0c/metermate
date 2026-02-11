"""
HDF (Harmonised Downloadable File) Parser for ESB Networks smart meter data.

Parses CSV files containing 30-minute interval electricity consumption data.
"""

import pandas as pd
from datetime import datetime
from typing import Tuple, Optional
import io


def parse_hdf_file(file_content: bytes | str | io.IOBase) -> pd.DataFrame:
    """
    Parse an ESB Networks HDF CSV file into a clean DataFrame.

    Args:
        file_content: CSV file content (bytes, string, or file-like object)

    Returns:
        DataFrame with columns:
        - datetime: Timezone-aware datetime (Europe/Dublin)
        - mprn: Meter Point Reference Number
        - import_kwh: Energy imported from grid
        - export_kwh: Energy exported to grid (solar)
        - hour: Hour of day (0-23)
        - day_of_week: Day name (Monday-Sunday)
        - day_of_week_num: Day number (0=Monday, 6=Sunday)
        - is_weekend: Boolean
        - month: Month name
        - year_month: YYYY-MM string
        - tariff_period: 'Night', 'Day', or 'Peak'
    """
    # Read CSV
    if isinstance(file_content, bytes):
        file_content = io.BytesIO(file_content)

    df = pd.read_csv(file_content)

    # Normalize column names (handle variations)
    df.columns = df.columns.str.strip()

    # Parse datetime - handle both DD-MM-YYYY and DD/MM/YYYY formats
    datetime_col = 'Read Date and End Time'

    # Try DD-MM-YYYY format first
    try:
        df['datetime'] = pd.to_datetime(df[datetime_col], format='%d-%m-%Y %H:%M')
    except ValueError:
        # Try DD/MM/YYYY format
        df['datetime'] = pd.to_datetime(df[datetime_col], format='%d/%m/%Y %H:%M')

    # Localize to Europe/Dublin - handle DST ambiguity by defaulting to standard time
    # This is acceptable for energy analysis purposes
    try:
        df['datetime'] = df['datetime'].dt.tz_localize('Europe/Dublin', ambiguous=False, nonexistent='shift_forward')
    except Exception:
        # Fallback: keep as naive datetime (timezone-unaware)
        pass

    # Extract MPRN
    df['mprn'] = df['MPRN'].astype(str)

    # Determine if kW or kWh format
    read_type_sample = df['Read Type'].iloc[0]
    is_kw_format = 'kW)' in read_type_sample and 'kWh' not in read_type_sample

    # Separate import and export
    import_mask = df['Read Type'].str.contains('Import', case=False)
    export_mask = df['Read Type'].str.contains('Export', case=False)

    # Create pivot with import and export as separate columns
    imports = df[import_mask][['datetime', 'mprn', 'Read Value']].copy()
    imports = imports.rename(columns={'Read Value': 'import_kwh'})

    exports = df[export_mask][['datetime', 'Read Value']].copy()
    exports = exports.rename(columns={'Read Value': 'export_kwh'})

    # Merge on datetime
    result = imports.merge(exports, on='datetime', how='left')
    result['export_kwh'] = result['export_kwh'].fillna(0)

    # Convert kW to kWh if needed (30-minute intervals, so divide by 2)
    if is_kw_format:
        result['import_kwh'] = result['import_kwh'] / 2
        result['export_kwh'] = result['export_kwh'] / 2

    # Sort by datetime
    result = result.sort_values('datetime').reset_index(drop=True)

    # Add time-based features
    result['hour'] = result['datetime'].dt.hour
    result['day_of_week'] = result['datetime'].dt.day_name()
    result['day_of_week_num'] = result['datetime'].dt.dayofweek
    result['is_weekend'] = result['day_of_week_num'] >= 5
    result['month'] = result['datetime'].dt.month_name()
    result['year_month'] = result['datetime'].dt.strftime('%Y-%m')
    result['date'] = result['datetime'].dt.date

    # Classify tariff period
    result['tariff_period'] = result['hour'].apply(classify_tariff_period)

    return result


def classify_tariff_period(hour: int) -> str:
    """
    Classify an hour into Irish electricity tariff periods.

    Night: 23:00 - 08:00
    Peak: 17:00 - 19:00
    Day: 08:00 - 17:00, 19:00 - 23:00
    """
    if hour >= 23 or hour < 8:
        return 'Night'
    elif 17 <= hour < 19:
        return 'Peak'
    else:
        return 'Day'


def get_summary_stats(df: pd.DataFrame) -> dict:
    """
    Calculate summary statistics from parsed HDF data.
    """
    total_import = df['import_kwh'].sum()
    total_export = df['export_kwh'].sum()

    # Date range
    date_range_days = (df['datetime'].max() - df['datetime'].min()).days

    # Daily averages
    daily_import = df.groupby('date')['import_kwh'].sum()
    avg_daily_import = daily_import.mean()

    # Night-time baseload (minimum during night hours)
    night_data = df[df['tariff_period'] == 'Night']
    if len(night_data) > 0:
        # Get minimum per night, then average those minimums
        night_mins = night_data.groupby('date')['import_kwh'].min()
        baseload_kwh = night_mins.mean()
        # Convert 30-min reading to hourly rate
        baseload_kw = baseload_kwh * 2
    else:
        baseload_kw = 0

    # Peak consumption
    peak_kwh = df['import_kwh'].max()
    peak_kw = peak_kwh * 2  # 30-min to hourly
    peak_time = df.loc[df['import_kwh'].idxmax(), 'datetime']

    # Tariff breakdown
    tariff_totals = df.groupby('tariff_period')['import_kwh'].sum()

    # Has solar
    has_solar = total_export > 0

    # Weekday vs weekend
    weekday_avg = df[~df['is_weekend']].groupby('date')['import_kwh'].sum().mean()
    weekend_avg = df[df['is_weekend']].groupby('date')['import_kwh'].sum().mean()

    return {
        'total_import_kwh': total_import,
        'total_export_kwh': total_export,
        'net_import_kwh': total_import - total_export,
        'date_range_days': date_range_days,
        'avg_daily_import_kwh': avg_daily_import,
        'baseload_kw': baseload_kw,
        'peak_kw': peak_kw,
        'peak_time': peak_time,
        'tariff_day_kwh': tariff_totals.get('Day', 0),
        'tariff_night_kwh': tariff_totals.get('Night', 0),
        'tariff_peak_kwh': tariff_totals.get('Peak', 0),
        'has_solar': has_solar,
        'weekday_avg_kwh': weekday_avg,
        'weekend_avg_kwh': weekend_avg,
        'mprn': df['mprn'].iloc[0],
        'start_date': df['datetime'].min(),
        'end_date': df['datetime'].max(),
    }


PROVIDER_PRESETS = {
    'Electric Ireland': {'day': 28.14, 'night': 14.79, 'peak': 30.02},
    'Energia':          {'day': 27.81, 'night': 15.29, 'peak': 31.22},
    'SSE Airtricity':   {'day': 28.29, 'night': 18.18, 'peak': 31.69},
    'Bord Gais Energy': {'day': 30.23, 'night': 22.31, 'peak': 36.79},
    'Flogas':           {'day': 26.02, 'night': 18.78, 'peak': 30.79},
    'Pinergy':          {'day': 38.32, 'night': 31.77, 'peak': 41.77},
    'Custom':           {'day': 28.14, 'night': 14.79, 'peak': 30.02},
}

# CEG (Clean Export Guarantee) rate - standard across all suppliers, VAT exempt
CEG_RATE_EUR = 0.185

# Hours per year by tariff period (for always-on baseload costing)
NIGHT_HOURS_YR = 3285
PEAK_HOURS_YR = 730
DAY_HOURS_YR = 4745


def _annual_baseload_cost_per_kw(rates: dict) -> float:
    """Annual cost of 1 kW always-on load using tariff period hours."""
    return (NIGHT_HOURS_YR * rates['night'] +
            PEAK_HOURS_YR * rates['peak'] +
            DAY_HOURS_YR * rates['day'])


def _blended_rate(rates: dict) -> float:
    """Weighted average rate using tariff period hour shares."""
    return (9/24 * rates['night'] + 2/24 * rates['peak'] + 13/24 * rates['day'])


def _parse_tariff_rates(tariff_rates: dict | None) -> dict:
    """Normalise tariff rates to EUR/kWh. Defaults to Electric Ireland SST."""
    if tariff_rates is None:
        preset = PROVIDER_PRESETS['Electric Ireland']
        return {k: v / 100 for k, v in preset.items()}
    # Already in EUR if values are < 1, otherwise convert from cents
    sample = next(iter(tariff_rates.values()))
    if sample > 1:
        return {k: v / 100 for k, v in tariff_rates.items()}
    return dict(tariff_rates)


def detect_anomalies(df: pd.DataFrame, tariff_rates: dict | None = None) -> list[dict]:
    """
    Detect potential anomalies in the consumption data.

    Args:
        df: Parsed HDF DataFrame with 30-min interval data.
        tariff_rates: Dict with 'day', 'night', 'peak' rates in EUR/kWh.
                      Defaults to Electric Ireland SST if None.

    Returns a list of anomaly dicts with type, title, description, severity,
    category, annual_cost_eur, recommendation, value, and chart_annotations.
    """
    rates = _parse_tariff_rates(tariff_rates)
    baseload_cost_per_kw = _annual_baseload_cost_per_kw(rates)
    blended = _blended_rate(rates)
    anomalies = []

    # Date range for annualisation
    date_range_days = max((df['datetime'].max() - df['datetime'].min()).days, 1)

    # Pre-compute common aggregates
    night_data = df[df['tariff_period'] == 'Night']
    daily_totals = df.groupby('date')['import_kwh'].sum()
    daily_mean = daily_totals.mean()
    daily_std = daily_totals.std() if len(daily_totals) > 1 else 0

    weekday_daily = df[~df['is_weekend']].groupby('date')['import_kwh'].sum()
    weekend_daily = df[df['is_weekend']].groupby('date')['import_kwh'].sum()
    weekday_avg = weekday_daily.mean() if len(weekday_daily) > 0 else 0
    weekend_avg = weekend_daily.mean() if len(weekend_daily) > 0 else 0

    # Night-time baseload (average of nightly minimum 30-min readings, in kW)
    baseload_kw = 0.0
    if len(night_data) > 0:
        night_mins = night_data.groupby('date')['import_kwh'].min()
        baseload_kw = night_mins.mean() * 2  # 30-min reading to kW

    # Absolute minimum (phantom load)
    absolute_min_kwh = df['import_kwh'].min()
    phantom_kw = absolute_min_kwh * 2

    # ───────────────────────────────────────────────────────────
    # ANOMALIES (problems to flag)
    # ───────────────────────────────────────────────────────────

    # 1. HIGH BASELOAD
    if baseload_kw > 0.5:
        cost = baseload_kw * baseload_cost_per_kw
        severity = 'warning' if baseload_kw < 1.0 else 'alert'
        anomalies.append({
            'type': 'high_baseload',
            'title': 'High Baseload',
            'description': f'Average always-on baseload is {baseload_kw:.2f} kW.',
            'severity': severity,
            'category': 'anomaly',
            'annual_cost_eur': cost,
            'recommendation': (
                f'Your always-on baseload of {baseload_kw:.2f} kW costs '
                f'~\u20ac{cost:,.0f}/year. Consider timer switches, standby '
                f'elimination, or equipment audit.'
            ),
            'value': baseload_kw,
            'chart_annotations': [
                {
                    'chart': 'baseload_chart',
                    'type': 'hline',
                    'params': {
                        'y': 0.5,
                        'line_dash': 'dash',
                        'line_color': '#f59e0b',
                        'line_width': 1.5,
                        'annotation_text': 'Warning threshold',
                        'annotation_position': 'right',
                        'annotation': {'font_color': '#f59e0b', 'font_size': 11},
                    },
                },
            ],
        })

    # 2. PHANTOM / ALWAYS-ON LOAD
    if phantom_kw > 0.2:
        cost = phantom_kw * baseload_cost_per_kw
        anomalies.append({
            'type': 'phantom_load',
            'title': 'Phantom Load',
            'description': (
                f'Absolute minimum consumption never drops below {phantom_kw:.2f} kW.'
            ),
            'severity': 'warning',
            'category': 'anomaly',
            'annual_cost_eur': cost,
            'recommendation': (
                f'Your absolute minimum consumption never drops below {phantom_kw:.2f} kW. '
                f'This phantom load costs \u20ac{cost:,.0f}/year. Check for always-on devices: '
                f'immersion heaters, dehumidifiers, server equipment.'
            ),
            'value': phantom_kw,
            'chart_annotations': [
                {
                    'chart': 'baseload_chart',
                    'type': 'hline',
                    'params': {
                        'y': phantom_kw,
                        'line_dash': 'dash',
                        'line_color': '#ef4444',
                        'line_width': 1.5,
                        'annotation_text': f'Phantom load: {phantom_kw:.2f} kW',
                        'annotation_position': 'right',
                        'annotation': {'font_color': '#ef4444', 'font_size': 11},
                    },
                },
            ],
        })

    # 3. CONSUMPTION SPIKES
    if daily_std > 0:
        spike_threshold = daily_mean + 2 * daily_std
        spike_days = daily_totals[daily_totals > spike_threshold]
        if len(spike_days) > 0:
            total_excess = (spike_days - daily_mean).sum()
            annual_excess = (total_excess / date_range_days) * 365
            cost = annual_excess * blended
            spike_dates_list = spike_days.index.tolist()[:5]

            chart_annots = []
            # vrect for each spike day
            for sd in spike_dates_list:
                chart_annots.append({
                    'chart': 'daily_trend',
                    'type': 'vrect',
                    'params': {
                        'x0': str(sd), 'x1': str(sd),
                        'fillcolor': '#ef4444', 'opacity': 0.15, 'line_width': 0,
                    },
                })
            # threshold hline
            chart_annots.append({
                'chart': 'daily_trend',
                'type': 'hline',
                'params': {
                    'y': spike_threshold,
                    'line_dash': 'dash',
                    'line_color': '#f59e0b',
                    'line_width': 1.5,
                    'annotation_text': 'Spike threshold',
                    'annotation_position': 'right',
                    'annotation': {'font_color': '#f59e0b', 'font_size': 11},
                },
            })

            anomalies.append({
                'type': 'consumption_spikes',
                'title': f'{len(spike_days)} Days with Unusual Spikes',
                'description': (
                    f'Found {len(spike_days)} days with consumption significantly '
                    f'above average ({daily_mean:.1f} kWh/day).'
                ),
                'severity': 'info',
                'category': 'anomaly',
                'annual_cost_eur': cost,
                'recommendation': (
                    f'{len(spike_days)} days had consumption significantly above average. '
                    f'Excess consumption costs ~\u20ac{cost:,.0f}/year. Investigate: were these '
                    f'legitimate (events, weather) or waste?'
                ),
                'value': len(spike_days),
                'spike_dates': spike_dates_list,
                'chart_annotations': chart_annots,
            })

    # 4. BASELOAD STEP-CHANGE
    daily_mins = df.groupby('date')['import_kwh'].min() * 2  # kW
    if len(daily_mins) >= 28:
        rolling_min = daily_mins.rolling(14, min_periods=7).mean()
        shifted = rolling_min.shift(7)
        # Only consider where both values are meaningful (> 0.05 kW)
        mask = (shifted > 0.05) & (rolling_min > 0.05)
        relative_shift = ((rolling_min - shifted) / shifted).where(mask)
        relative_shift = relative_shift.dropna()

        significant = relative_shift[relative_shift.abs() > 0.25]
        if len(significant) > 0:
            # Take the largest shift
            idx = significant.abs().idxmax()
            change_pct = relative_shift.loc[idx] * 100
            before_val = shifted.loc[idx]
            after_val = rolling_min.loc[idx]
            delta_kw = after_val - before_val
            is_increase = delta_kw > 0

            cost = abs(delta_kw) * baseload_cost_per_kw if is_increase else 0
            severity = 'warning' if is_increase else 'info'

            desc_direction = 'increased' if is_increase else 'decreased'
            anomalies.append({
                'type': 'baseload_step_change',
                'title': 'Baseload Step-Change',
                'description': (
                    f'Baseload {desc_direction} from {before_val:.2f} kW to '
                    f'{after_val:.2f} kW around {idx} ({change_pct:+.0f}%).'
                ),
                'severity': severity,
                'category': 'anomaly' if is_increase else 'insight',
                'annual_cost_eur': cost,
                'recommendation': (
                    f'Baseload shifted from {before_val:.2f} kW to {after_val:.2f} kW around {idx}. '
                    + (f'This adds \u20ac{cost:,.0f}/year. Possible causes: new equipment installed, '
                       f'heating system left on, faulty thermostat.' if is_increase
                       else 'This represents a saving — good work!')
                ),
                'value': delta_kw,
                'chart_annotations': [
                    {
                        'chart': 'baseload_chart',
                        'type': 'vrect',
                        'params': {
                            'x0': str(idx), 'x1': str(idx),
                            'fillcolor': '#f59e0b', 'opacity': 0.15, 'line_width': 0,
                            'annotation_text': f'{change_pct:+.0f}%',
                            'annotation_position': 'top left',
                            'annotation': {'font_color': '#f59e0b', 'font_size': 11},
                        },
                    },
                ],
            })

    # 5. MORNING RAMP TOO EARLY
    if 'hour' in df.columns:
        weekday_df = df[~df['is_weekend']]
        if len(weekday_df) > 0:
            early_morning = weekday_df[(weekday_df['hour'] >= 5) & (weekday_df['hour'] < 6)]
            early_avg_kw = early_morning['import_kwh'].mean() * 2 if len(early_morning) > 0 else 0

            if baseload_kw > 0 and early_avg_kw > baseload_kw * 1.5:
                excess_kw = early_avg_kw - baseload_kw
                cost = 1 * excess_kw * rates['day'] * 365  # 1 hour early
                # Find typical ramp hour
                hourly_avg = weekday_df.groupby('hour')['import_kwh'].mean() * 2
                daily_range = hourly_avg.max() - baseload_kw
                if daily_range > 0:
                    ramp_threshold = baseload_kw + 0.5 * daily_range
                    ramp_hours = hourly_avg[hourly_avg > ramp_threshold].index
                    ramp_hour = int(ramp_hours.min()) if len(ramp_hours) > 0 else 6

                    anomalies.append({
                        'type': 'morning_ramp',
                        'title': 'Early Morning Ramp',
                        'description': (
                            f'Equipment appears to start around {ramp_hour:02d}:00, '
                            f'which may be earlier than needed.'
                        ),
                        'severity': 'info',
                        'category': 'anomaly',
                        'annual_cost_eur': cost,
                        'recommendation': (
                            f'Equipment appears to start around {ramp_hour:02d}:00, which may be '
                            f'earlier than needed. Adjusting start time could save '
                            f'\u20ac{cost:,.0f}/year.'
                        ),
                        'value': ramp_hour,
                        'chart_annotations': [
                            {
                                'chart': 'daily_profile',
                                'type': 'vrect',
                                'params': {
                                    'x0': ramp_hour, 'x1': 8,
                                    'fillcolor': '#f59e0b', 'opacity': 0.15,
                                    'line_width': 0,
                                    'annotation_text': 'Early start',
                                    'annotation_position': 'top left',
                                    'annotation': {'font_color': '#f59e0b', 'font_size': 11},
                                },
                            },
                        ],
                    })

    # 6. EVENING TAIL TOO LATE
    if 'hour' in df.columns:
        late_evening = df[(df['hour'] >= 22) & (df['hour'] < 23)]
        late_avg_kw = late_evening['import_kwh'].mean() * 2 if len(late_evening) > 0 else 0

        if baseload_kw > 0 and late_avg_kw > baseload_kw * 1.5:
            excess_kw = late_avg_kw - baseload_kw
            cost = 1 * excess_kw * rates['day'] * 365
            anomalies.append({
                'type': 'evening_tail',
                'title': 'Late Evening Tail',
                'description': (
                    f'Consumption remains elevated ({late_avg_kw:.2f} kW) at 22:00, '
                    f'well above baseload ({baseload_kw:.2f} kW).'
                ),
                'severity': 'info',
                'category': 'anomaly',
                'annual_cost_eur': cost,
                'recommendation': (
                    f'Consumption remains elevated until 22:00, well above baseload. '
                    f'Earlier shutdown could save \u20ac{cost:,.0f}/year.'
                ),
                'value': late_avg_kw,
                'chart_annotations': [
                    {
                        'chart': 'daily_profile',
                        'type': 'vrect',
                        'params': {
                            'x0': 19, 'x1': 23,
                            'fillcolor': '#f59e0b', 'opacity': 0.15,
                            'line_width': 0,
                            'annotation_text': 'Late shutdown',
                            'annotation_position': 'top right',
                            'annotation': {'font_color': '#f59e0b', 'font_size': 11},
                        },
                    },
                ],
            })

    # ───────────────────────────────────────────────────────────
    # INSIGHTS (observations with savings potential)
    # ───────────────────────────────────────────────────────────

    # 7. WEEKEND VS WEEKDAY
    if weekday_avg > 0 and weekend_avg > weekday_avg * 1.2:
        excess_per_day = weekend_avg - weekday_avg
        cost = excess_per_day * 104 * blended  # 104 weekend days/year
        anomalies.append({
            'type': 'high_weekend_usage',
            'title': 'Higher Weekend Usage',
            'description': (
                f'Weekend usage ({weekend_avg:.1f} kWh/day) is '
                f'{((weekend_avg / weekday_avg) - 1) * 100:.0f}% higher than '
                f'weekday ({weekday_avg:.1f} kWh/day).'
            ),
            'severity': 'info',
            'category': 'insight',
            'annual_cost_eur': cost,
            'recommendation': (
                f'Excess weekend consumption costs ~\u20ac{cost:,.0f}/year. '
                f'Investigate whether weekend loads can be reduced or shifted.'
            ),
            'value': weekend_avg / weekday_avg,
            'chart_annotations': [],
        })

    # 8. PEAK PERIOD OVERUSE
    total_kwh = df['import_kwh'].sum()
    if total_kwh > 0:
        peak_data = df[df['tariff_period'] == 'Peak']
        peak_kwh = peak_data['import_kwh'].sum()
        peak_share = peak_kwh / total_kwh

        if peak_share > 0.12:
            expected_share = 2 / 24  # ~8.3%
            total_annual = (total_kwh / date_range_days) * 365
            excess_annual = (peak_share - expected_share) * total_annual
            cost = excess_annual * (rates['peak'] - rates['day'])
            severity = 'warning' if peak_share > 0.18 else 'info'

            anomalies.append({
                'type': 'peak_overuse',
                'title': 'Peak Period Overuse',
                'description': (
                    f'{peak_share * 100:.1f}% of consumption falls in peak hours '
                    f'(17:00-19:00) vs expected ~8%.'
                ),
                'severity': severity,
                'category': 'insight',
                'annual_cost_eur': cost,
                'recommendation': (
                    f'{peak_share * 100:.1f}% of your consumption falls in peak hours '
                    f'(17:00-19:00) vs expected 8%. Shifting to off-peak could save '
                    f'\u20ac{cost:,.0f}/year.'
                ),
                'value': peak_share,
                'chart_annotations': [],
            })

    # 9. TARIFF OPTIMISATION
    if total_kwh > 0:
        tariff_totals = df.groupby('tariff_period')['import_kwh'].sum()
        night_kwh = tariff_totals.get('Night', 0)
        peak_kwh_val = tariff_totals.get('Peak', 0)
        day_kwh = tariff_totals.get('Day', 0)

        actual_cost = (night_kwh * rates['night'] +
                       peak_kwh_val * rates['peak'] +
                       day_kwh * rates['day'])
        flat_cost = total_kwh * rates['day']  # day rate as flat proxy

        annual_actual = (actual_cost / date_range_days) * 365
        annual_flat = (flat_cost / date_range_days) * 365
        saving = annual_flat - annual_actual

        if saving > 0:
            anomalies.append({
                'type': 'tariff_optimisation',
                'title': 'Smart Tariff Benefit',
                'description': (
                    f'Your smart tariff saves \u20ac{saving:,.0f}/year vs a flat rate.'
                ),
                'severity': 'info',
                'category': 'insight',
                'annual_cost_eur': 0,
                'recommendation': f'Your smart tariff saves you \u20ac{saving:,.0f}/year vs flat rate.',
                'value': saving,
                'chart_annotations': [],
            })
        elif saving < -10:
            loss = abs(saving)
            anomalies.append({
                'type': 'tariff_optimisation',
                'title': 'Smart Tariff Disadvantage',
                'description': (
                    f'You\'d save \u20ac{loss:,.0f}/year on a flat rate tariff.'
                ),
                'severity': 'warning',
                'category': 'insight',
                'annual_cost_eur': loss,
                'recommendation': (
                    f'You\'d save \u20ac{loss:,.0f}/year on a flat rate tariff. '
                    f'Your usage pattern doesn\'t benefit from smart tariff.'
                ),
                'value': -loss,
                'chart_annotations': [],
            })

    # 10. SOLAR SELF-CONSUMPTION
    if df['export_kwh'].sum() > 0:
        daytime_mask = (df['hour'] >= 8) & (df['hour'] < 18)
        daytime_export = df[daytime_mask]['export_kwh'].sum()
        daytime_import = df[daytime_mask]['import_kwh'].sum()
        total_export = df['export_kwh'].sum()

        # Annual export credit
        annual_export = (total_export / date_range_days) * 365
        export_credit = annual_export * CEG_RATE_EUR

        # Battery potential
        daily_avg_export = total_export / date_range_days
        battery_capture = daily_avg_export * 0.6  # 60% capture rate
        battery_saving = battery_capture * rates['day'] * 365

        if daytime_export > daytime_import * 0.5:
            anomalies.append({
                'type': 'low_self_consumption',
                'title': 'Consider Battery Storage',
                'description': (
                    f'Exporting {daytime_export:.1f} kWh during daytime. '
                    f'Current export earns \u20ac{export_credit:,.0f}/year at the CEG rate.'
                ),
                'severity': 'info',
                'category': 'insight',
                'annual_cost_eur': battery_saving,
                'recommendation': (
                    f'You\'re exporting {annual_export:,.0f} kWh/year worth '
                    f'\u20ac{export_credit:,.0f}/year at the CEG rate. A battery storing '
                    f'{battery_capture:.1f} kWh/day could save an additional '
                    f'\u20ac{battery_saving:,.0f}/year by self-consuming at the day rate instead.'
                ),
                'value': daytime_export,
                'chart_annotations': [],
            })

    # 11. SEASONAL VARIATION
    if 'year_month' in df.columns:
        monthly_kwh = df.groupby('year_month')['import_kwh'].sum()
        if len(monthly_kwh) >= 3:
            monthly_rolling = monthly_kwh.rolling(3, center=True, min_periods=1).mean()
            deviation = (monthly_kwh - monthly_rolling) / monthly_rolling
            anomalous = deviation[deviation > 0.3]

            if len(anomalous) > 0:
                worst_month = anomalous.idxmax()
                worst_pct = anomalous.max() * 100
                excess_kwh = (monthly_kwh[worst_month] -
                              monthly_rolling[worst_month])
                cost = excess_kwh * blended

                anomalies.append({
                    'type': 'seasonal_variation',
                    'title': 'Seasonal Anomaly',
                    'description': (
                        f'{worst_month} consumption was {worst_pct:.0f}% above the '
                        f'seasonal trend.'
                    ),
                    'severity': 'info',
                    'category': 'insight',
                    'annual_cost_eur': cost,
                    'recommendation': (
                        f'{worst_month} consumption was {worst_pct:.0f}% above the '
                        f'seasonal trend. This added \u20ac{cost:,.0f}. Investigate: '
                        f'weather event, occupancy change, or equipment issue?'
                    ),
                    'value': worst_pct,
                    'chart_annotations': [
                        {
                            'chart': 'monthly_trend',
                            'type': 'annotation',
                            'params': {
                                'x': worst_month,
                                'y': float(monthly_kwh[worst_month]),
                                'text': f'{worst_pct:.0f}% above trend',
                                'showarrow': True,
                                'arrowcolor': '#3b82f6',
                                'arrowwidth': 1.5,
                                'font': {'color': '#3b82f6', 'size': 11},
                                'bgcolor': 'rgba(0,0,0,0.5)',
                            },
                        },
                    ],
                })

    return anomalies


def get_summary_stats_flexible(df: pd.DataFrame, granularity) -> dict:
    """
    Calculate summary statistics with graceful degradation by granularity.

    For interval data (30min/hourly), delegates to get_summary_stats().
    For daily/monthly, computes a reduced stat set (no baseload, peak, tariff).
    """
    from parse_result import DataGranularity

    if granularity in (DataGranularity.HALF_HOURLY, DataGranularity.HOURLY):
        return get_summary_stats(df)

    # Reduced stats for daily/monthly data
    total_import = df['import_kwh'].sum() if 'import_kwh' in df.columns else 0
    total_export = df['export_kwh'].sum() if 'export_kwh' in df.columns else 0

    date_range_days = 0
    start_date = None
    end_date = None
    if 'datetime' in df.columns and len(df) > 0:
        start_date = df['datetime'].min()
        end_date = df['datetime'].max()
        date_range_days = (end_date - start_date).days

    # Daily average
    if granularity == DataGranularity.DAILY and 'date' in df.columns:
        daily_import = df.groupby('date')['import_kwh'].sum()
        avg_daily_import = daily_import.mean()
    elif date_range_days > 0:
        avg_daily_import = total_import / max(date_range_days, 1)
    else:
        avg_daily_import = total_import

    # Weekday vs weekend (only for daily+)
    weekday_avg = 0.0
    weekend_avg = 0.0
    if 'is_weekend' in df.columns and 'date' in df.columns:
        weekday_data = df[~df['is_weekend']]
        weekend_data = df[df['is_weekend']]
        if len(weekday_data) > 0:
            weekday_avg = weekday_data.groupby('date')['import_kwh'].sum().mean()
        if len(weekend_data) > 0:
            weekend_avg = weekend_data.groupby('date')['import_kwh'].sum().mean()
    elif 'is_weekend' in df.columns:
        weekday_data = df[~df['is_weekend']]
        weekend_data = df[df['is_weekend']]
        weekday_avg = weekday_data['import_kwh'].mean() if len(weekday_data) > 0 else 0
        weekend_avg = weekend_data['import_kwh'].mean() if len(weekend_data) > 0 else 0

    mprn = df['mprn'].iloc[0] if 'mprn' in df.columns and len(df) > 0 else 'Unknown'

    return {
        'total_import_kwh': total_import,
        'total_export_kwh': total_export,
        'net_import_kwh': total_import - total_export,
        'date_range_days': date_range_days,
        'avg_daily_import_kwh': avg_daily_import,
        'baseload_kw': None,
        'peak_kw': None,
        'peak_time': None,
        'tariff_day_kwh': None,
        'tariff_night_kwh': None,
        'tariff_peak_kwh': None,
        'has_solar': total_export > 0,
        'weekday_avg_kwh': weekday_avg if weekday_avg else avg_daily_import,
        'weekend_avg_kwh': weekend_avg if weekend_avg else avg_daily_import,
        'mprn': mprn,
        'start_date': start_date,
        'end_date': end_date,
    }


def detect_anomalies_flexible(df: pd.DataFrame, granularity, tariff_rates: dict | None = None) -> list[dict]:
    """
    Detect anomalies with graceful degradation by granularity.

    For interval data, delegates to detect_anomalies().
    For daily, runs weekend/spike detection.
    For monthly, runs monthly outlier detection.
    """
    from parse_result import DataGranularity

    if granularity in (DataGranularity.HALF_HOURLY, DataGranularity.HOURLY):
        return detect_anomalies(df, tariff_rates=tariff_rates)

    anomalies = []

    if granularity == DataGranularity.DAILY:
        # Weekend vs weekday (if we have day info)
        if 'is_weekend' in df.columns and 'date' in df.columns:
            weekday_avg = df[~df['is_weekend']].groupby('date')['import_kwh'].sum().mean()
            weekend_avg = df[df['is_weekend']].groupby('date')['import_kwh'].sum().mean()

            if weekday_avg > 0 and weekend_avg > weekday_avg * 1.2:
                anomalies.append({
                    'type': 'high_weekend_usage',
                    'title': 'Higher Weekend Usage',
                    'description': f'Weekend usage ({weekend_avg:.1f} kWh/day) is higher than '
                                  f'weekday ({weekday_avg:.1f} kWh/day).',
                    'severity': 'info',
                    'value': weekend_avg / weekday_avg,
                })

        # Consumption spikes
        if 'import_kwh' in df.columns:
            daily_totals = df.groupby('date')['import_kwh'].sum() if 'date' in df.columns else df['import_kwh']
            daily_mean = daily_totals.mean()
            daily_std = daily_totals.std()

            if daily_std > 0:
                spike_days = daily_totals[daily_totals > daily_mean + 2 * daily_std]
                if len(spike_days) > 0:
                    anomalies.append({
                        'type': 'consumption_spikes',
                        'title': f'{len(spike_days)} Days with Unusual Spikes',
                        'description': f'Found {len(spike_days)} days with consumption significantly '
                                      f'above average ({daily_mean:.1f} kWh/day).',
                        'severity': 'info',
                        'value': len(spike_days),
                        'spike_dates': list(spike_days.index)[:5],
                    })

    elif granularity == DataGranularity.MONTHLY:
        # Monthly outliers
        if 'import_kwh' in df.columns:
            monthly_mean = df['import_kwh'].mean()
            monthly_std = df['import_kwh'].std()

            if monthly_std > 0:
                outliers = df[df['import_kwh'] > monthly_mean + 2 * monthly_std]
                if len(outliers) > 0:
                    anomalies.append({
                        'type': 'monthly_outliers',
                        'title': f'{len(outliers)} Months with Unusual Consumption',
                        'description': f'Found {len(outliers)} months significantly above average '
                                      f'({monthly_mean:.0f} kWh/month).',
                        'severity': 'info',
                        'value': len(outliers),
                    })

    return anomalies
