%nprocshared=12
%mem=24GB
# M062X/Def2TZVP freq=noraman opt=(calcfc,ts,noeigen,maxstep=5)

TS_2_imag_freq

0 3
 C   0.07721000   1.30179400   0.15388600
 C   1.56216800   1.20388500   0.01060300
 C   2.23740000   0.00484300  -0.02066900
 C   1.55133400  -1.19448400   0.11171400
 C   0.07263000  -1.25832500   0.30863100
 C  -0.63296500   0.00207500  -0.11410600
 C  -2.12620400   0.01345200  -0.25324500
 C  -2.90759100   1.24690900   0.09393600
 C  -2.87076600  -1.28724900  -0.14489300
 H   2.11968700   2.13038100  -0.05650900
 H   2.10533200  -2.12580500   0.11520700
 H  -0.14108000  -1.45402400   1.37736700
 H  -0.32675400  -2.12910100  -0.21539100
 H  -1.27112900   0.02528000  -1.24700800
 H  -3.09401400   1.29583700   1.17566600
 H  -2.40247200   2.16960500  -0.18557400
 H  -3.88181200   1.23800500  -0.40069800
 H  -3.89351300  -1.16614400  -0.50190400
 H  -2.92517100  -1.63484000   0.89477500
 H  -2.41509000  -2.08510100  -0.72944100
 H  -0.16739900   1.66657100   1.16714800
 C   3.73781600  -0.01939000  -0.17814700
 H   4.02763300  -0.62236900  -1.04794400
 H   4.13617300   0.99110600  -0.31262500
 H   4.21424600  -0.46286400   0.70594700
 H  -0.28884100   2.08240900  -0.51927000

