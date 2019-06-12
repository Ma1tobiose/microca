# encoding=utf-8
from OpenSSL import crypto

import random
from datetime import datetime
import os

# import sys
#
# reload(sys)
# sys.setdefaultencoding('utf8')

rnd = random.Random()


def rand_serial(n_bits=160):
    """
    :param n_bits: Generate a random serial number. The default
    size of the serial number is 160 bits which is as good as a UUID
    uniqueness
    """
    return rnd.randint(0, 2 ** n_bits)


def genkey(n_bits):
    """ generates an RSA PEM key of n_bits size
    """
    pkey = crypto.PKey()
    pkey.generate_key(crypto.TYPE_RSA, n_bits)
    key = crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey)
    return key


def gencsr(subj_name, key):
    """ Takes in a subject name and Pem encoded key and generates a CSR
    example subjname "cn=www.somehost.com,ST=Texas,L=San Antonio, O=Rackspace, OU=Rackspace hosting,C=US"
    """
    # Convert the pem key to a lowlevel OpenSSL key
    pkey = crypto.load_privatekey(crypto.FILETYPE_PEM, key)
    req = crypto.X509Req()
    allowed_oids = set(["CN", "ST", "L", "O", "OU", "C"])
    # split the string up so we can add it to one by one into the subj attrs
    subj = req.get_subject()
    for oid_and_value in subj_name.split(","):
        oid, value = oid_and_value.split("=")
        if oid.upper() in allowed_oids:
            setattr(subj, oid.strip().upper(), value.strip())

    # Attach the public key
    req.set_pubkey(pkey)

    # sign the CSR with its own key with a sha1 signature
    req.sign(pkey, "sha1")

    # Return the pem encoding of the CSR
    return crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)


def self_sign_csr(csr, key, validity_secs=24 * 60 * 60):
    """ Generate a self signed root certificate.
    in this case the subject is pulled from the csr and placed
    in the new cert.
    """
    priv_key = crypto.load_privatekey(crypto.FILETYPE_PEM, key)
    pcsr = crypto.load_certificate_request(crypto.FILETYPE_PEM, csr)
    pub_key = pcsr.get_pubkey()
    if pcsr.verify(pub_key) == -1:
        raise Exception("csr didn't even sign its own key")
    subj = pcsr.get_subject()
    x509 = crypto.X509()
    x509.set_version(2)
    x509.set_serial_number(rand_serial())
    x509.set_subject(pcsr.get_subject())
    x509.set_issuer(pcsr.get_subject())
    x509.set_pubkey(pcsr.get_pubkey())
    x509.add_extensions(get_exts(ca=True))
    x509.gmtime_adj_notBefore(0)
    x509.gmtime_adj_notAfter(validity_secs)
    x509.sign(priv_key, "sha1")
    return crypto.dump_certificate(crypto.FILETYPE_PEM, x509)


def sign_csr(csr, ca_key, ca_crt, validity_secs=180 * 24 * 60 * 60, ca=True):
    """ Sign the CSR with the ca key and cert
    the ca boolean specifies if the certificate is allowed to sign other certs
    """
    ca_PKey = crypto.load_privatekey(crypto.FILETYPE_PEM, ca_key)
    ca_x509 = crypto.load_certificate(crypto.FILETYPE_PEM, ca_crt)
    pcsr = crypto.load_certificate_request(crypto.FILETYPE_PEM, csr)

    x509 = crypto.X509()
    pub_key = pcsr.get_pubkey()
    x509.set_version(2)
    x509.set_serial_number(rand_serial())
    x509.set_pubkey(pub_key)
    x509.set_subject(pcsr.get_subject())
    x509.set_issuer(ca_x509.get_subject())
    x509.gmtime_adj_notBefore(0)
    x509.gmtime_adj_notAfter(validity_secs)
    x509.add_extensions(get_exts(ca=ca))
    x509.sign(ca_PKey, "sha1")
    return crypto.dump_certificate(crypto.FILETYPE_PEM, x509)


def get_exts(ca=True):
    ca_sign = 'digitalSignature, keyEncipherment,  Data Encipherment, Certificate Sign'
    ca_no_sign = 'digitalSignature, keyEncipherment,  Data Encipherment'
    if ca:
        exts = [crypto.X509Extension('keyUsage', True, ca_sign),
                crypto.X509Extension('basicConstraints', True, 'CA:true')]
    else:
        exts = [crypto.X509Extension('keyUsage', True, ca_no_sign),
                crypto.X509Extension('basicConstraints', True, 'CA:false')]
    return exts


def p12(certdata, privkeydata, user_name, password):
    cert = crypto.load_certificate(crypto.FILETYPE_PEM, certdata)
    privkey = crypto.load_privatekey(crypto.FILETYPE_PEM, privkeydata)
    pfx = crypto.PKCS12Type()
    pfx.set_privatekey(privkey)
    pfx.set_certificate(cert)
    pfxdata = pfx.export(password)
    with open('/opt/microCA/users/' + user_name + '.p12', 'w') as pfxfile:
        pfxfile.write(pfxdata)
    return pfxdata


def get_cert_details(dirpath, cert_file, password_dic):
    # path表示证书路径，file_name表示证书文件名
    file_ext = cert_file.split('.')[-1]
    if file_ext == 'pfx' or file_ext == 'p12':
        pfx = crypto.load_pkcs12(open(os.path.join(dirpath, cert_file)).read(), password_dic[cert_file][0])
        cert = pfx.get_certificate()
    if file_ext == 'cer' or file_ext == 'pem':
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, open(os.path.join(dirpath, cert_file)).read())
    subject = cert.get_subject()
    # 得到证书的域名
    issued_to = subject.CN
    issuer = cert.get_issuer()
    # 得到证书颁发机构
    issued_by = issuer.CN
    end_time = datetime.strptime(cert.get_notAfter()[:-1], "%Y%m%d%H%M%S")
    start_time = datetime.strptime(cert.get_notBefore()[:-1], "%Y%m%d%H%M%S")
    return issued_to, issued_by, start_time, end_time

