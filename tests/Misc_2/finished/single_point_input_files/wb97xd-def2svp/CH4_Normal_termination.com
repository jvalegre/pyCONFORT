%mem=96GB
%nprocshared=24
# wb97xd/def2svp NBO

 CH4

3 5
 C   0.00000000   0.00000000   0.00000000
 H   0.63133100   0.63133100   0.63133100
 H  -0.63133100  -0.63133100   0.63133100
 H  -0.63133100   0.63133100  -0.63133100
 H   0.63133100  -0.63133100  -0.63133100

$NBO $END

