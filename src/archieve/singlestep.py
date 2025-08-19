# -*- coding: utf-8 -*-
"""
Created on Mon May 30 16:15:46 2022
@author: cukelarter

Script for initiating single-step basic run on Chemyx Syringe Pump. Tested on Chemyx 100-X.

After importing serial connection driver we connect to the pump. Connection will remain open
until user calls "conn.closeConnection()". If user does not call this before exiting
the connection will remain locked open until the connection is physically broken (unplugged).
The run will continue to completion after connection is closed.

"""
#%% Import CHEMYX serial connection module/driver
from core import connect

# get open port info
portinfo = connect.getOpenPorts() 
#%%
# MUST set baudrate in pump "System Settings", and MUST match this rate:
baudrate=38400
# initiate Connection object with first open port
conn = connect.Connection(port="COM5",baudrate=baudrate, x=0, mode=0, verbose=True)


#%%


conn.open_CON_NICK()
#conn.openConnection()

#%%

conn.ser.isOpen()

#%%

resp = conn.getParameters()


#%%

start_pump = conn.startPump()




#%%
stop_pump = conn.stopPump()

# Parameters for the syringes in use:

conn.setVolume(1) # 1ml Syringe
conn.setDiameter(4.64) # 1ml syringe has 4.64mm diameter
conn.setUnits('mL/hr')
conn.setRate(60) # 60 mL/hr