#!/usr/bin/env python3 -tt

from Crypto.Hash import MD4
import binascii
import hashlib
import hmac
from pyasn1.type import univ, char, useful, tag
from pyasn1.codec.ber import encoder, decoder
import datetime
import base64
import sys

#REF: http://tools.ietf.org/id/draft-brezak-win2k-krb-rc4-hmac-03.txt

#T = 1 for TS-ENC-TS in the AS-Request 
#T = 8 for the AS-Reply  
#T = 7 for the Authenticator in the TGS-Request 
#T = 8 for the TGS-Reply  
#T = 2 for the Server Ticket in the AP-Request 
#T = 11 for the Authenticator in the AP-Request 
#T = 12 for the Server returned AP-Reply 
#T = 15 in the generation of checksum for the MIC token 
#T = 0 in the generation of sequence number for the MIC token  
#T = 13 in the generation of checksum for the WRAP token 
#T = 0 in the generation of sequence number for the WRAP token  
#T = 0 in the generation of encrypted data for the WRAPPED token


def ntlmhash(s):
    hash = MD4.new()
    hash.update(s.encode('utf-16le'))
    digest = hash.digest()
    return binascii.hexlify(digest).upper().decode('utf-8')
    #return binascii.hexlify(hash)

def rc4crypt(key, data):
    x = 0
    box = list(range(256))
    for i in range(256):
        x = (x + box[i] + (key[i % len(key)])) % 256
        box[i], box[x] = box[x], box[i]
    x = 0
    y = 0
    out = b''
    for char in data:
        x = (x + 1) % 256
        y = (y + box[x]) % 256
        box[x], box[y] = box[y], box[x]
        out += bytes([char ^ box[(box[x] + box[y]) % 256]])
    return out



#print decoder.decode(enc)

#define KERB_ETYPE_RC4_HMAC             23
KERB_ETYPE_RC4_HMAC = 23
#define KERB_ETYPE_RC4_HMAC_EXP         24

def decrypt(key, messagetype, edata):
    #DECRYPT (K, fRC4_EXP, T, edata, edata_len, data, data_len) 
    #{ 
    #    if (fRC4_EXP){ 
    #        *((DWORD *)(L40+10)) = T; 
    #        HMAC (K, L40, 14, K1); 
    #    }else{ 
    #        HMAC (K, &T, 4, K1); 
    #    } 
    #K1 = hmac.new(key, chr(messagetype) + "\x00\x00\x00", hashlib.md5).digest() # \x0b = 11
    key_bytes = bytes.fromhex(key) if len(key) == 32 else key.encode('utf-8')
    K1 = hmac.new(key_bytes, bytes([messagetype]) + b"\x00\x00\x00", hashlib.md5).digest()
    #    memcpy (K2, K1, 16); 
    K2 = K1

    #    if (fRC4_EXP) memset (K1+7, 0xAB, 9); 
    #    HMAC (K1, edata, 16, K3); // checksum is at edata 
    K3 = hmac.new(K1, edata[:16], hashlib.md5).digest()
    #    RC4(K3, edata + 16, edata_len - 16, edata + 16); 
    ddata = rc4crypt(K3, edata[16:])
    #    data_len = edata_len - 16 - 8; 
    #    memcpy (data, edata + 16 + 8, data_len);
    #     
    #    // verify generated and received checksums 
    #    HMAC (K2, edata + 16, edata_len - 16, checksum); 
    checksum = hmac.new(K2, ddata, hashlib.md5).digest()
    #    if (memcmp(edata, checksum, 16) != 0)  
    #        printf("CHECKSUM ERROR  !!!!!!\n"); 
    #}
    if checksum == edata[:16]: 
        #print "Decrypt Checksum: %s" % str(checksum).encode('hex') # == edata[:16])
        #print "Checksum Calc: %s" % str(checksum).encode('hex')
        #print "Checksum Pkct: %s" % str(edata[:16]).encode('hex')
        #print messagetype
        #print data
        #print "Nonce: %s" % ddata[:8].encode('hex')
        #return ddata[8:] # first 8 bytes are nonce, the rest is data
        #return { 
        #    'data': ddata[8:],
        #    'nonce': ddata[:8]
        #}
        return ddata[8:], ddata[:8]
    else:
        #print "CHECKSUM ERROR!"
        return None, None

def encrypt(key, messagetype, data, nonce):
    #  if (fRC4_EXP){ 
    #      *((DWORD *)(L40+10)) = T; 
    #      HMAC (K, L40, 10 + 4, K1); 
    #  }else{ 
    #      HMAC (K, &T, 4, K1); 
    #  }
    K1 = hmac.new(key, bytes(messagetype) + b'\x00\x00\x00', hashlib.md5).digest() # \x0b = 11
    #  memcpy (K2, K1, 16);
    K2 = K1 
    #  if (fRC4_EXP) memset (K1+7, 0xAB, 9); 
    #  add_8_random_bytes(data, data_len, conf_plus_data); 
    ddata = nonce + data
    #  HMAC (K2, conf_plus_data, 8 + data_len, checksum); 
    checksum = hmac.new(K2, ddata, hashlib.md5).digest()
    #  HMAC (K1, checksum, 16, K3); 
    K3 = hmac.new(K1, checksum, hashlib.md5).digest()
    #print "K3: %s" % K3.encode('hex')
    
    #  RC4(K3, conf_plus_data, 8 + data_len, edata + 16); 
    # print "EN DDATA: %s" % ddata[:32].encode('hex')
    edata = rc4crypt(K3, ddata)
    
    #  memcpy (edata, checksum, 16); 
    #  edata_len = 16 + 8 + data_len; 
    return checksum + edata

def zerosigs(data):
    d = list(map(ord, str(data)))
    for i in range(5, 21): # zero out the 16 char sig, KDC
        d[len(d) - i] = 0
    for i in range(29, 45): # zero out the 16 char sig, Server
        d[len(d) - i] = 0

    retval = "".join(map(chr, d))
    #print retval.encode('hex')


    return bytearray(retval,"utf-8")

def chksum(K, T, data):
    data = zerosigs(data)

    # K = the Key
    #T = the message type, encoded as a little-endian four-byte integer

    #Ksign = HMAC(K, "signaturekey")  //includes zero octet at end
    SIGNATUREKEY = b'signaturekey\x00'
    Ksign = hmac.new(K, SIGNATUREKEY, hashlib.md5).digest()
    #tmp = MD5(concat(T, data))
    tmp = hashlib.md5(T + data).digest()
    #CHKSUM = HMAC(Ksign, tmp)
    chksum = hmac.new(Ksign, tmp, hashlib.md5).digest()
    return chksum

def getservsig(encchunk):
    return str(encchunk[-44:-28])

def getprivsig(encchunk):
    return str(encchunk[-20:-4])

def printdecode(kerbpayload, ktype=2):
    d = decoder.decode(kerbpayload)
    if ktype == 32:
        #print "Protocol Version (pvno):  " + str(d[0][0])
        print("Message Type:             " + str(d[0][1]))
        print("Realm:                    " + str(d[0][2]))
        print("Principal:                " + str(d[0][3][1][0]))
        print("Ticket Version (tkt-vno): " + str(d[0][4][0]))
        print("Ticket Realm:             " + str(d[0][4][1]))
        #print "Name-Type (Service & Instance): " + str(d[0][4][2][0])
        print("Server, Name:             " + str(d[0][4][2][1][0]))
        print("Server, Name:             " + str(d[0][4][2][1][1]))
        #print "Data:                     " + str(d[0][4][3][2]).encode('hex')

        #print "Encryption Type: :        " + str(d[0][5][0])
        #print "Data:                     " + str(d[0])
        #print "Server Realm:             " + str(d[0][4][2][4])
    elif ktype == 2:
        print("a")

def extract_ticket_from_kirbi(filename):
    with open(filename, 'rb') as fd:
        data = fd.read()
        return extract_ticket(data)

def extract_ticket(data):
    if data[0] == 0x76:
        # ram dump 
        #enctickets.append(((decoder.decode(data)[0][2][0][3][2]).asOctets(), i, f))
        return (decoder.decode(data)[0][2][0][3][2]).asOctets()
    elif data[:2] == b'6d':
        # honestly, i completely forgot. I think this is from a pcap -Tim
        #enctickets.append(((decoder.decode(ticket.decode('hex'))[0][4][3][2]).asOctets(), i, f))
        return (decoder.decode(ticket.decode('hex'))[0][4][3][2]).asOctets()

