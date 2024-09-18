import pandas as pd
import numpy as np

def reconcile_data(file1_path, file2_path):
    # Load the CSV or Excel files into DataFrames
    mutasi = pd.read_csv(file1_path, skiprows=9) if file1_path.endswith('.csv') else pd.read_excel(file1_path, skiprows=9)
    gds = pd.read_csv(file2_path) if file2_path.endswith('.csv') else pd.read_excel(file2_path)

    # Process mutasi
    mutasi['Mutation Format'] = mutasi['Description'].str.split(' ').str[6]
    mutasi['Mutation Format_number'] = mutasi['Description'].str.split(' ').str[7]
    mutasi['Mutation Format'] = mutasi['Mutation Format'].astype(str) + ' ' + mutasi['Mutation Format_number'].astype(str)
    mutasi = mutasi.drop(['Mutation Format_number'], axis=1)

    mutasi['Credit'] = mutasi['Credit'].str.replace(',', '')
    mutasi['Credit'] = mutasi['Credit'].astype(str).astype(float)

    mutasi['Debit'] = mutasi['Debit'].str.replace(',', '')
    mutasi['Debit'] = mutasi['Debit'].astype(str).astype(float)

    debit = mutasi[mutasi['Credit'] == 0]
    debitcost = debit.copy()
    debitcost.loc[:,'Cost Date'] = debitcost.loc[:,'Description'].str.split('-').str[2].str.split(' ').str[0]
    costshopee = debitcost[debitcost['Description'].str.lower().str.contains('shopee')].index
    costdana = debitcost[debitcost['Description'].str.lower().str.contains('dana')].index
    costlinkaja = debitcost[debitcost['Description'].str.lower().str.contains('linkaja')].index
    debitcost.loc[costshopee, 'Payment Vendor'] = 'shopee'
    debitcost.loc[costdana, 'Payment Vendor'] = 'dana'
    debitcost.loc[costlinkaja, 'Payment Vendor'] = 'linkaja'
    nanindex = debitcost[debitcost['Payment Vendor'].isna()].index
    debitcost = debitcost.drop(nanindex)
    debitcost = debitcost.groupby(['Cost Date', 'Payment Vendor']).agg({'Debit' : 'sum'} )
    debitcost = debitcost.reset_index()
    costdebitshopee = debitcost[debitcost['Payment Vendor'].str.lower().str.contains('shopee')].index

    costdebitdana = debitcost[debitcost['Payment Vendor'].str.lower().str.contains('dana')].index

    costdebitlinkaja = debitcost[debitcost['Payment Vendor'].str.lower().str.contains('linkaja')].index

    debitcost.loc[costdebitshopee, 'Trx'] = debitcost['Debit'] / 334
    debitcost.loc[costdebitdana, 'Trx'] = debitcost['Debit'] / 334
    debitcost.loc[costdebitlinkaja, 'Trx'] = debitcost['Debit'] / 223

    indexdebit = mutasi[mutasi['Credit'] == 0].index
    mutasi = mutasi.drop(indexdebit)
    credit = mutasi.copy()

    indexpbb = mutasi[mutasi['Description'].str.lower().str.contains('pbb')].index
    mutasi = mutasi.drop(indexpbb)
    indexmutasidana = mutasi[mutasi['Description'].str.lower().str.contains('dana')].index
    indexmutasilinkaja = mutasi[mutasi['Description'].str.lower().str.contains('linkaja')].index
    indexmutasishopee = mutasi[mutasi['Description'].str.lower().str.contains('shopee')].index
    mutasi.loc[indexmutasidana, 'Payment Vendor'] = 'dana'

    mutasi.loc[indexmutasilinkaja, 'Payment Vendor'] = 'linkaja'

    mutasi.loc[indexmutasishopee, 'Payment Vendor'] = 'shopee'

    mutasi['Credit'] = mutasi['Credit'] - 1000
    credit['Credit'] = credit['Credit'] - 1000

    gdsraw = gds
    gdsnotsuccess = gds[gds['internal_transaction_status'] != 'SUCCESS']
    indexgdsfailed = gds[gds['internal_transaction_status'] != 'SUCCESS'].index
    gds = gds.drop(indexgdsfailed)

    data_compare = pd.merge(mutasi, gds, left_on = ['Mutation Format', 'Credit'], right_on = ['ocbc_mutation_format', 'amount'], how = 'outer', indicator = True)
    data_compare['Match?'] = np.where((data_compare['Mutation Format'] == data_compare['ocbc_mutation_format']) & (data_compare['Credit'] == data_compare['amount']), 'Recon', 'Unrecon')
    datacomparetemp = data_compare.copy()
    datacomparetemp['_merge'] = datacomparetemp['_merge'].astype(str)
    unreconmutasi = datacomparetemp[datacomparetemp['_merge'] == 'left_only']
    unrecongds = datacomparetemp[datacomparetemp['_merge'] == 'right_only']
    unreconindex = data_compare[data_compare['Match?'] == 'Unrecon'].index
    data_compare = data_compare.drop(unreconindex)
    temp = gdsnotsuccess[['ocbc_mutation_format', 'id', 'transaction_status']].copy()
    unreconmutasi = pd.merge(unreconmutasi, temp, left_on = 'Mutation Format', right_on = 'ocbc_mutation_format', how = 'left' )
    summarygds = gdsraw.copy()
    summarygds = summarygds[summarygds['internal_transaction_status'] == 'SUCCESS']
    summarymutasi = credit.copy()
    indexdana = summarymutasi[summarymutasi['Description'].str.lower().str.contains('dana')].index
    indexlinkaja = summarymutasi[summarymutasi['Description'].str.lower().str.contains('linkaja')].index
    indexshopee = summarymutasi[summarymutasi['Description'].str.lower().str.contains('shopee')].index
    summarymutasi.loc[indexdana, 'Payment Vendor'] = 'dana'
    summarymutasi.loc[indexlinkaja, 'Payment Vendor'] = 'linkaja'
    summarymutasi.loc[indexshopee, 'Payment Vendor'] = 'shopee'
    # indexother = summarymutasi[summarymutasi['Payment Vendor'] == 'nan'].index
    pivotmutasi = summarymutasi.groupby(['Value Date', 'Payment Vendor']).agg({'Mutation Format':'count','Credit':'sum'})
    pivotmutasi = pivotmutasi.reset_index()
    pivotmutasi.rename(columns = {'Mutation Format' : "#Trx"}, inplace = True)
    summarygds['last_updated_datetime'] = pd.to_datetime(summarygds['last_updated_datetime']).dt.date
    pivotgds = summarygds.groupby(['last_updated_datetime','bank_code']).agg({'partner_transaction_id':'count','amount':'sum'})
    pivotgds = pivotgds.reset_index()
    pivotgds.rename(columns = {'partner_transaction_id' : "#Trx"}, inplace = True)


    # Example of dynamic sheet names based on the module's logic
    sheet_dict = {
        "Mutasi Debit" :debit,
        "Mutasi Credit" : credit,
        "GDS RAW" : gdsraw,
        "Line Per Line": data_compare,
        "Unrecon Mutasi": unreconmutasi,
        "Unrecon GDS": unrecongds,
        "Pivot Mutasi": pivotmutasi,
        "Pivot GDS" : pivotgds,
        "Cost" : debitcost
        # Add more sheets as required
    }



    return sheet_dict
