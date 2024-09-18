import pandas as pd
import numpy as np

def reconcile_data(file1_path, file2_path):
    # Load the CSV or Excel files into DataFrames
    df1 = pd.read_csv(file1_path) if file1_path.endswith('.csv') else pd.read_excel(file1_path)
    df2 = pd.read_csv(file2_path) if file2_path.endswith('.csv') else pd.read_excel(file2_path)

    dashraw = df1
    gdsraw = df2
    indexwd = df1[df1['Transaction Type'] == 'Organization Withdraw of Funds with Next Working Day'].index
    wd = df1[df1['Transaction Type'] == 'Organization Withdraw of Funds with Next Working Day']
    df1 = df1.drop(indexwd)
    indexcost = df1[df1['Transaction Scenario'] == 'Physical Merchant Fee 46'].index
    cost = df1[df1['Credit'] == 0.0]
    cost = cost[['Orderid', 'Debit']].copy()
    df1 = df1.drop(indexcost)
    df1 = pd.merge(df1, cost, on ='Orderid', how = 'outer')
    df1 = df1[['Biz Org Name', 'Orderid', 'Trans End Time', 'Transaction Type', 'Transaction Scenario', 'Trans Status',
            'Credit', 'Debit_y']].copy()
    df1.rename(columns = {'Debit_y' : 'Debit'}, inplace = True)
    df1 = df1.add_suffix('_df1')
    df2 = df2.add_suffix('_df2')
    reconciled_df = pd.merge(df1, df2, left_on = 'Orderid_df1', right_on = 'tx_serial_number_df2', how = 'outer', indicator = True )
    reconciled_df['Match?'] = np.where((reconciled_df['Orderid_df1'] == reconciled_df['tx_serial_number_df2']) & (reconciled_df['Credit_df1'] == reconciled_df['amount_df2']), 'Recon', 'Unrecon')
    realtimesettleindex = reconciled_df[reconciled_df['settlement_time_df2'].isna()].index

    reconciled_df.loc[realtimesettleindex, 'settlement_time_df2'] = reconciled_df['last_updated_datetime_df2']

    reconciled_df.loc[realtimesettleindex, 'settlement_time_df2'] = pd.to_datetime(reconciled_df['settlement_time_df2']).dt.date
    unrecon = reconciled_df[reconciled_df['Match?'] == 'Unrecon']

    indexunrecon = reconciled_df[reconciled_df['Match?'] == 'Unrecon'].index

    reconciled_df = reconciled_df.drop(indexunrecon)
    summary = reconciled_df
    summary['last_updated_datetime_df2'] = pd.to_datetime(summary['last_updated_datetime_df2']).dt.date

    summary['settlement_time_df2'] = pd.to_datetime(summary['settlement_time_df2']).dt.date

    summary['transaction_datetime_df2'] = pd.to_datetime(summary['transaction_datetime_df2']).dt.date
    summary = summary.groupby(['last_updated_datetime_df2', 'transaction_datetime_df2','settlement_time_df2', 'username_df2', 'service_df2', 'mam_parent_username_df2', 'mam_child_username_df2', 'vendor_code_df2'], dropna = False).agg({'Orderid_df1':'count','amount_df2' : 'sum', 'admin_fee_df2' : 'sum','admin_fee_invoice_df2' : 'sum', 'Debit_df1' :'sum', 'deduction_cost_df2' : 'sum','settlement_amount_df2' :'sum' })
    summary.rename(columns = {'Orderid_df1' : "#Trx"}, inplace = True)

    summary = summary.reset_index()

    summary['last_updated_datetime_df2'] = pd.to_datetime(summary['last_updated_datetime_df2']).dt.date

    summary['settlement_time_df2'] = pd.to_datetime(summary['settlement_time_df2']).dt.date 

    sheet_dict = {
        "Dashboard Raw" : dashraw,
        "GDS Raw" : gdsraw,
        "Line Per Line": reconciled_df,
        "Unrecon": unrecon,
        "Summary" :summary
        # Add more sheets as required
    }
    
    return sheet_dict
