import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')


def main():
    INPUT = 'sg_household_input_8760h.xlsx'
    OUTPUT = 'sg_household_output_8760.xlsx'

    # Years to include in the output
    BASE_YEAR = 2022
    FORECAST_YEARS = list(range(2023, 2051))
    ALL_YEARS = [BASE_YEAR] + FORECAST_YEARS

    HOUSE_TYPES = ['HDB 1-2', 'HDB 3', 'HDB 4', 'HDB 5', 'Condo/Apt', 'Landed', 'Other']
    H8760_COLS = [f'Hour {i}' for i in range(8760)]

    print(f"Loading data from {INPUT}...")


    def load_and_sanitize(sheet):
        df = pd.read_excel(INPUT, sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    app_master = load_and_sanitize('1_ApplianceMaster')
    power_ratings = load_and_sanitize('2_PowerRatings').set_index('Appliance')
    penetration = load_and_sanitize('3_Penetration').set_index('Appliance')
    age_mults = load_and_sanitize('4_AgeMultipliers').set_index('Appliance')
    hourly_profiles = load_and_sanitize('5_HourlyProfiles').set_index('Appliance')
    hourly_forecasts = load_and_sanitize('9_HourlyProfileForecasts8760h')
    hh_counts = load_and_sanitize('6_HouseholdCounts').set_index('House Type')
    age_dist = load_and_sanitize('7_AgeDistribution')
    efficiency = load_and_sanitize('8_Efficiency').set_index('House Type')

    results_list = []

    timeseries_data = {year: np.zeros(8760) for year in ALL_YEARS}

    print(f"Starting calculation for {ALL_YEARS[0]} to {ALL_YEARS[-1]}...")

    for year in ALL_YEARS:
        y_str = str(year)

        for h_type in HOUSE_TYPES:
            n_hh = float(hh_counts.loc[h_type, y_str])
            eff_factor = float(efficiency.loc[h_type, y_str])

            # Filter age distribution
            age_sub = age_dist[age_dist['House Type'] == h_type]
            age_shares = {
                '65': float(age_sub[age_sub['Age Group'] == '65+'][y_str].values[0]),
                '15-64': float(age_sub[age_sub['Age Group'] == '15-64'][y_str].values[0]),
                '15': float(age_sub[age_sub['Age Group'] == '<15'][y_str].values[0])
            }

            for _, app_row in app_master.iterrows():
                app = app_row['Appliance']
                fuel = app_row['FuelType']

                # Retrieve ratings
                p_rating = float(power_ratings.loc[app, f'{h_type} kW'])
                pen_rate = float(penetration.loc[app, y_str])

                # Weighted age multiplier
                a_mult = (float(age_mults.loc[app, 'Age 65 Multiplier']) * age_shares['65'] +
                          float(age_mults.loc[app, 'Age 15-64 Multiplier']) * age_shares['15-64'] +
                          float(age_mults.loc[app, 'Age 15 Multiplier']) * age_shares['15'])

                # Load profile and yearly adjustments
                static_profile = hourly_profiles.loc[app, H8760_COLS].values
                yr_forecast = hourly_forecasts[(hourly_forecasts['Appliance'] == app) &
                                               (hourly_forecasts['Year'].astype(str) == y_str)]

                f_values = yr_forecast[H8760_COLS].values.flatten() if not yr_forecast.empty else np.ones(8760)

                # Compute hourly demand in kW for this specific group
                hourly_kw = static_profile * f_values * p_rating * pen_rate * a_mult * eff_factor * n_hh

                # Add to total hourly time series (for the whole system)
                timeseries_data[year] += hourly_kw

                # Sum annual demand for tabular sheets
                annual_twh = np.sum(hourly_kw) / 1e9

                results_list.append({
                    'Year': year, 'Housing Type': h_type, 'Energy Carrier': fuel,
                    'Appliance': app, 'Demand (TWh)': round(annual_twh, 6)
                })

    # Prepare DataFrames
    df_full = pd.DataFrame(results_list)

    # Create the Time Series DataFrame
    ts_rows = []
    for year in ALL_YEARS:
        ts_rows.append([year] + timeseries_data[year].tolist())

    df_timeseries = pd.DataFrame(ts_rows, columns=['Year'] + [f'Hour {i + 1}' for i in range(8760)])

    # Save to Excel
    print(f"Saving to {OUTPUT}...")
    with pd.ExcelWriter(OUTPUT) as writer:
        df_full.groupby(['Year', 'Housing Type'])['Demand (TWh)'].sum().reset_index().to_excel(writer, 'By_HousingType',
                                                                                               index=False)
        df_full.groupby(['Year', 'Energy Carrier'])['Demand (TWh)'].sum().reset_index().to_excel(writer,
                                                                                                 'By_EnergyCarrier',
                                                                                                 index=False)
        df_full.groupby(['Year', 'Appliance'])['Demand (TWh)'].sum().reset_index().to_excel(writer, 'By_Appliance',
                                                                                            index=False)
        df_timeseries.to_excel(writer, 'Total_Energy_TimeSeries', index=False)
        df_full.to_excel(writer, 'Full_Detailed_Breakdown', index=False)

    print("Success: 2022-2050 Forecast Complete.")


if __name__ == "__main__":
    main()