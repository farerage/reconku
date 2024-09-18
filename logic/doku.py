import pandas as pd
import numpy as np
from sqlalchemy import create_engine

db_uri = 'postgresql://postgres:fgerry@localhost:5432/doku'

def reconcile_data(file1_path, file2_path):
    # Load the CSV or Excel files into DataFrames

    engine = create_engine(db_uri)

    dfs = []
    df1 = pd.read_csv(file1_path[0], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'}) if file1_path[0].endswith('.csv') else pd.read_excel(file1_path[0], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'})
    df2 = pd.read_csv(file1_path[1], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'}) if file1_path[1].endswith('.csv') else pd.read_excel(file1_path[1], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'})
    dfs.append(df1)
    dfs.append(df2)
    if len(file1_path) > 2:
        df3 = file1_path[2]
        df3 = pd.read_csv(file1_path[2], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'}) if file1_path[2].endswith('.csv') else pd.read_excel(file1_path[2], skiprows=2, dtype = {'Recon Code' : 'str', 'Invoice Number' : 'str'})
        dfs.append(df3)
    else:
        df3 = None

    gds = pd.read_csv(file2_path) if file2_path.endswith('.csv') else pd.read_excel(file2_path)

    dash = pd.concat(dfs).reset_index(drop = True)
    dash['Total Amount'] = dash['Total Amount'].str.replace(',','')
    dash['Total Amount'] = dash['Total Amount'].astype(str).astype(float)

    dash['Total Fee'] = dash['Total Fee'].str.replace(',','')
    dash['Total Fee'] = dash['Total Fee'].astype(str).astype(float)

    dash['Net Amount'] = dash['Net Amount'].str.replace(',','')
    dash['Net Amount'] = dash['Net Amount'].astype(str).astype(float)

    dashraw = dash.copy()
    gdsraw = gds.copy()

    gds = gds.add_suffix('_GDS')
    dash = dash.add_suffix('_DASH')

    reconciled_df = pd.merge(dash,gds, left_on='Invoice Number_DASH', right_on='unique_id_GDS', how='outer', indicator=True)

    reconciled_df['Match?'] = np.where((reconciled_df['Invoice Number_DASH'] == reconciled_df['unique_id_GDS']) & (reconciled_df['Total Amount_DASH'] == reconciled_df['amount_GDS']) , "Recon", "Unrecon")

    realtimesettleindex = reconciled_df[reconciled_df['settlement_time_GDS'].isna()].index

    reconciled_df.loc[realtimesettleindex, 'settlement_time_GDS'] = reconciled_df['last_updated_datetime_GDS']

    unrecon = reconciled_df[reconciled_df['Match?'] == 'Unrecon']

    index_unrecon = reconciled_df[reconciled_df['Match?'] == 'Unrecon'].index

    reconciled_df = reconciled_df.drop(index_unrecon)

    summary = reconciled_df

    summary['last_updated_datetime_GDS'] = pd.to_datetime(summary['last_updated_datetime_GDS']).dt.date
    summary['settlement_time_GDS'] = pd.to_datetime(summary['settlement_time_GDS']).dt.date

    summary = summary.groupby(['last_updated_datetime_GDS', 'settlement_time_GDS', 'username_GDS', 'Acquirer_DASH', 'service_GDS', 'vendor_GDS'], dropna = False).agg({'Invoice Number_DASH':'count','amount_GDS' : 'sum', 'admin_fee_GDS' : 'sum','admin_fee_invoice_GDS' : 'sum', 'Total Fee_DASH' :'sum', 'deduction_cost_GDS' : 'sum', 'settlement_amount_GDS' :'sum' })

    summary.rename(columns = {'Invoice Number_DASH' : "#Trx"}, inplace = True)

    summary = summary.reset_index()


    summary['settlement_time_GDS'] = pd.to_datetime(summary['settlement_time_GDS']).dt.date


    sheet_dict = {
        "dashboard_raw" : dashraw,
        "gds_raw" : gdsraw,
        "reconciled": reconciled_df,
        "unrecon": unrecon,
        "summary" : summary
       # Add more sheets as required
    }

    for table_name, df in sheet_dict.items():
        df.to_sql(table_name, engine, if_exists='append', index=False)
        print(f"DataFrame '{table_name}' has been stored in the PostgreSQL database.")

    return sheet_dict

    