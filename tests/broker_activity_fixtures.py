"""Synthetic broker "all transactions" exports (structure of the real files; invented figures, names and accounts).

Fidelity: ``history_csv``. E*Trade: ``etrade_csv``. Vanguard: ``vanguard_csv`` (two accounts in one file).
"""

HEADER = ("Run Date,Action,Symbol,Description,Type,Price ($),Quantity,Commission ($),Fees ($),Accrued Interest ($),"
          "Amount ($),Cash Balance ($),Settlement Date")

FOOTER = '''
"The data and information in this spreadsheet is provided to you solely for your use and is not for distribution."
"Brokerage services are provided by an example broker. Not tax advice."

Date downloaded 10/28/2026 1:00 pm'''

ROWS = [
    '09/30/2026,REINVESTMENT FIDELITY GOVERNMENT CASH RESERVES (FDRXX) (Cash),FDRXX,FIDELITY GOVERNMENT CASH RESERVES,Cash,1,0.12,"","","","-0.12",50.00,""',
    '09/30/2026,DIVIDEND RECEIVED FIDELITY GOVERNMENT CASH RESERVES (FDRXX) (Cash),FDRXX,FIDELITY GOVERNMENT CASH RESERVES,Cash,"",0,"","","",0.12,50.00,""',
    '09/18/2026,REINVESTMENT EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,100.5,2,"","","","-201",49.88,""',
    '09/18/2026,DIVIDEND RECEIVED EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,"",0,"","","",201,250.88,""',
    '09/17/2026,RETURN EXCESS CONTR HSA CHK PD 000000001 (Cash),"",No Description,Cash,"",0,"","","","-100",49.88,""',
    '09/15/2026,YOU SOLD EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,110,"-1","","","",110,149.88,09/16/2026',
    '08/12/2026,YOU SOLD EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,105,"-0.5","","","",52.5,39.88,08/13/2026',
    '08/12/2026,YOU SOLD EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,105,"-6","",0.03,"",629.97,-12.62,08/13/2026',
    '05/12/2026,YOU BOUGHT EXAMPLE TOTAL MARKET ETF (TOTL) (Cash),TOTL,EXAMPLE TOTAL MARKET ETF,Cash,100,10,"","","","-1000",0,05/13/2026',
    '05/11/2026,YOU SOLD EXAMPLE SHORT TREASURY (SHRT) (Cash),SHRT,EXAMPLE SHORT TREASURY,Cash,50,"-20","",0.05,"",999.95,1000,05/12/2026',
    '05/06/2026,DIVIDEND RECEIVED EXAMPLE SHORT TREASURY (SHRT) (Cash),SHRT,EXAMPLE SHORT TREASURY,Cash,"",0,"","","",4.5,0.05,""',
    '01/16/2026,PARTIC CONTR CURRENT PARTIC CONTRB CURRENT0000000 /WEB (Cash),"",No Description,Cash,"",0,"","","",1000,1000,""',
]


def history_csv(rows=None) -> str:
    return "﻿\n\n" + HEADER + "\n" + "\n".join(ROWS if rows is None else rows) + "\n" + FOOTER + "\n"


FILE_NAME = "History_for_Account_X12345678.csv"


# ------------------------------------------------------------------------------------------------------- E*Trade
ETRADE_HEADER = ("Activity/Trade Date,Transaction Date,Settlement Date,Activity Type,Description,Symbol,Cusip,Quantity #,"
                 "Price $,Amount $,Commission,Category,Note")
ETRADE_ACCOUNT = "etrade:9876"

ETRADE_ROWS = [
    "10/01/2026,10/01/2026,10/02/2026,Interest Income,MORGAN STANLEY PRIVATE BANK USD BANK DEPOSIT PROGRAM,MSPBNA,--,--,--,0.07,0.0,--,--",
    "09/18/2026,09/18/2026,--,Dividend,EXAMPLE TOTAL MARKET ETF,TOTL,--,--,--,201.00,0.0,--,--",
    "09/15/2026,09/15/2026,09/16/2026,Sold,EXAMPLE TOTAL MARKET ETF,TOTL,--,-1.5,110.0,164.9,0.1,--,--",
    "09/15/2026,09/15/2026,09/16/2026,Sold,EXAMPLE TOTAL MARKET ETF,TOTL,--,-2,110.0,220.0,0.0,--,--",
    "08/20/2026,08/20/2026,--,Redemption,EXAMPLE WARRANT,91733P115,--,-1000,--,10.0,0.0,--,--",
    "07/10/2026,07/10/2026,07/13/2026,Bought,EXAMPLE TREASURY BILL DUE 01/01/27,912797AA1,--,5000,98.5,-4925.0,0.0,--,--",
    "06/10/2026,06/10/2026,06/11/2026,Bought,EXAMPLE TOTAL MARKET ETF,TOTL,--,10,100.0,-1000.0,0.0,--,--",
    "06/01/2026,06/01/2026,--,Contribution,TY 2026 EMPLOYER CURR YR,--,--,--,--,500.0,0.0,--,--",
    "05/01/2026,05/01/2026,--,Service Fee,OUTGOING WIRE FEE,--,--,--,--,-25.0,0.0,--,--",
]

ETRADE_FOOTER = '''
"Under the Bank Deposit Program, free credit balances held in an account may be deposited with banks."
'''


def etrade_csv(rows=None, account_line="Account Activity for Rollover IRA -9876 from 2026-01-01 to 2026-10-30") -> str:
    return ("All Transactions Activity Types\n\n" + account_line + "\n\nTotal:,123.45\n\n" + ETRADE_HEADER + "\n"
            + "\n".join(ETRADE_ROWS if rows is None else rows) + "\n" + ETRADE_FOOTER)


ETRADE_FILE_NAME = "DownloadTxnHistory (9).csv"


# ------------------------------------------------------------------------------------------------------- Vanguard
VANGUARD_HEADER = ("Account Number,Trade Date,Settlement Date,Transaction Type,Transaction Description,Investment Name,"
                   "Symbol,Shares,Share Price,Principal Amount,Commissions and Fees,Net Amount,Accrued Interest,Account Type")
VANGUARD_ACCOUNTS = ("vanguard:1111", "vanguard:2222")

VANGUARD_ROWS = [
    # account 11111111
    "11111111,9/30/2026,9/30/2026,Dividend,Dividend Received,EXAMPLE EXTENDED MARKET ETF,EXMK,0,1,43.11,0,43.11,0,CASH",
    "11111111,9/30/2026,9/30/2026,Reinvestment,Dividend Reinvestment,EXAMPLE EXTENDED MARKET ETF,EXMK,0.2,215.55,-43.11,0,-43.11,0,CASH",
    "11111111,9/15/2026,9/16/2026,Sell,Sell,EXAMPLE EXTENDED MARKET ETF,EXMK,-5,200,1000,0.5,999.5,0,CASH",
    "11111111,9/15/2026,9/15/2026,Sweep in,Sweep Into Settlement Fund,EXAMPLE FEDERAL MONEY MARKET,VMFXX,0,1,-999.5,0,-999.5,0,CASH",
    "11111111,8/1/2026,8/1/2026,Conversion (outgoing),Partial Conversion,EXAMPLE MORNINGSTAR FUND,EXMS,-10,0,-2000,0,-2000,0,CASH",
    "11111111,7/1/2026,7/1/2026,Interest,Interest Received,EXAMPLE SR VAR FUND,,0,0,8.41,0,8.41,0,CASH",
    # account 22222222
    "22222222,9/30/2026,9/30/2026,Dividend,Dividend Received,EXAMPLE FEDERAL MONEY MARKET,VMFXX,0,1,2.5,0,2.5,0,CASH",
    "22222222,9/30/2026,9/30/2026,Reinvestment,Dividend Reinvestment,EXAMPLE FEDERAL MONEY MARKET,VMFXX,2.5,1,-2.5,0,-2.5,0,CASH",
    "22222222,6/2/2026,6/3/2026,Buy,Buy,EXAMPLE EXTENDED MARKET ETF,EXMK,4,210,-840,0,-840,0,CASH",
    "22222222,6/2/2026,6/3/2026,Sell,Sell,EXAMPLE SHORT BOND ETF,EXSB,-3,80,240,0,240,0,CASH",
    "22222222,4/7/2026,4/7/2026,Withdrawal,Withdrawal via Electronic Bank,CASH,,0,0,-500,0,-500,0,CASH",
]


def vanguard_csv(rows=None) -> str:
    return "﻿" + VANGUARD_HEADER + "\n" + "\n".join(VANGUARD_ROWS if rows is None else rows) + "\n"


VANGUARD_FILE_NAME = "OfxDownload.csv"
