import numpy as np
import zipfile
import os
import shutil
trace_zip_filename = 'trace_array.zip'
textin_zip_filename = 'textin_array.zip'
temp_dir = 'extracted_data'
os.makedirs(temp_dir, exist_ok=True)
with zipfile.ZipFile(trace_zip_filename, 'r') as zip_ref:
    zip_ref.extract('trace_array.npy', path=temp_dir)
with zipfile.ZipFile(textin_zip_filename, 'r') as zip_ref:
    zip_ref.extract('textin_array.npy', path=temp_dir)
trace_array = np.load(os.path.join(temp_dir, 'trace_array.npy'))
textin_array = np.load(os.path.join(temp_dir, 'textin_array.npy'))
shutil.rmtree(temp_dir)


SBOXES = [[12, 4, 6, 2, 10, 5, 11, 9, 14, 8, 13, 7, 0, 3, 15, 1],
        [6, 8, 2, 3, 9, 10, 5, 12, 1, 14, 4, 7, 11, 13, 0, 15],
        [11, 3, 5, 8, 2, 15, 10, 13, 14, 1, 7, 4, 12, 9, 6, 0],
        [12, 8, 2, 1, 13, 4, 15, 6, 7, 0, 10, 5, 3, 14, 9, 11],
        [7, 15, 5, 10, 8, 1, 6, 13, 0, 9, 3, 14, 11, 4, 2, 12],
        [5, 13, 15, 6, 9, 2, 12, 10, 11, 7, 8, 1, 4, 3, 14, 0],
        [8, 14, 2, 5, 6, 9, 1, 12, 15, 4, 11, 0, 13, 10, 3, 7],
        [1, 7, 14, 13, 0, 5, 8, 3, 4, 15, 10, 6, 9, 12, 11, 2]]

def apply_sbox(s, _in):
    return (
    (s[0][(_in >> 0) & 0x0F] << 0) +
    (s[1][(_in >> 4) & 0x0F] << 4) +
    (s[2][(_in >> 8) & 0x0F] << 8) +
    (s[3][(_in >> 12) & 0x0F] << 12) +
    (s[4][(_in >> 16) & 0x0F] << 16) +
    (s[5][(_in >> 20) & 0x0F] << 20) +
    (s[6][(_in >> 24) & 0x0F] << 24) +
    (s[7][(_in >> 28) & 0x0F] << 28)
    )

def bytes_to_int(inputdata):
    data = bytearray(inputdata)
    return int.from_bytes(data[0:4][::-1], byteorder='big'), int.from_bytes(data[4:8][::-1], byteorder='big')


def modular_add(x, y, mod=2 ** 32):
    res = x + int(y)
    return res if res < mod else res - mod

def shift_left_11(x):
    return ((x << 11) & (2 ** 32 - 1)) | (x >> (32 - 11))

def feistel_round(key, inputdata, round_index):
    _in = modular_add(inputdata, key)
    sbox_output = apply_sbox(SBOXES, _in)
    return (sbox_output >> (8 * round_index)) & 0xFF

def feistel(key, inputdata, nrounds):
    w = bytearray(key)
    x = [
        w[0 + i * 4] |
        w[1 + i * 4] << 8 |
        w[2 + i * 4] << 16 |
        w[3 + i * 4] << 24 for i in range(8)
    ]
    l, r = bytes_to_int(inputdata)
    if nrounds == 0:
        l, r = r, l
    else:
        for i in range(nrounds):
            l, r = shift_left_11(apply_sbox(SBOXES, modular_add(r, x[i]))) ^ l, l
    return l

HW = [bin(n).count("1") for n in range(256)]

def mean(X):
    return np.sum(X, axis=0)/len(X)

def std_dev(X, X_bar):
    return np.sqrt(np.sum((X-X_bar)**2, axis=0))

def cov(X, X_bar, Y, Y_bar):
    return np.sum((X-X_bar)*(Y-Y_bar), axis=0)

t_bar = np.sum(trace_array, axis=0)/len(trace_array)
o_t = np.sqrt(np.sum((trace_array - t_bar)**2, axis=0))

cparefs = [0] * 32 #put your key byte g3
bestguess = [0] * 32 #put your key byte guesses here

numt = len(trace_array) #number of traces
nump = np.shape(trace_array)[1] #number of trace points
round_data = np.zeros((numt, 8), dtype=int)

for rnum in range(8):
    bestround = 0
    for tnum_r in range(numt):
        round_data[tnum_r][rnum] = feistel(bestguess, textin_array[tnum_r], rnum)
    for bnum in reversed(range(4)):
        cpaoutput = np.zeros(256)
        maxcpa = np.zeros(256)
        for kguess in range(256):
            bestroundkey = kguess << (bnum * 8) | bestround
            hws = np.array([[HW[feistel_round(bestroundkey, round_data[tnum][rnum], bnum)] for tnum in range (numt)]]).transpose()
            hws_bar = mean(hws)
            o_hws = std_dev(hws, hws_bar)
            correlation = cov(trace_array, t_bar, hws, hws_bar)
            cpaoutput = correlation / (o_t * o_hws)
            maxcpa[kguess] = max(abs(cpaoutput))
        bestround = bestround | (np.argmax(maxcpa) << (bnum * 8))
        bestguess[((rnum + 1) * 4) - bnum - 1] = np.argmax(maxcpa)
        for b in bestguess: print("%02x " % b, end="")
        print("/n")
        cparefs[((rnum + 1) * 4) - bnum - 1] = max(maxcpa)
        for tnum_r in range(numt):
            round_data[tnum_r][rnum] = feistel(bestguess, textin_array[tnum_r], rnum)
print("Best Key Guess: ", end="")
for b in bestguess: print("%02x " % b, end="")
