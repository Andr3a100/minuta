"""L'elenco dei certificatori qualificati (lezione 16), su un elenco di prova
con la struttura di quello di AgID: un servizio qualificato attivo, uno
cessato, una marca temporale."""

from __future__ import annotations

from minuta import certificatori

T = "http://uri.etsi.org/TrstSvc"


def servizio(tipo: str, stato: str, *certificati: str) -> str:
    identita = "".join(
        f"<DigitalId><X509Certificate>{c}</X509Certificate></DigitalId>"
        for c in certificati
    )
    return (
        "<TSPService><ServiceInformation>"
        f"<ServiceTypeIdentifier>{T}/Svctype/{tipo}</ServiceTypeIdentifier>"
        f"<ServiceDigitalIdentity>{identita}</ServiceDigitalIdentity>"
        f"<ServiceStatus>{T}/TrustedList/Svcstatus/{stato}</ServiceStatus>"
        "</ServiceInformation></TSPService>"
    )


def prestatore(nome: str, *servizi: str) -> str:
    return (
        "<TrustServiceProvider><TSPInformation><TSPName>"
        f"<Name xml:lang='it'>{nome}</Name></TSPName></TSPInformation>"
        f"<TSPServices>{''.join(servizi)}</TSPServices>"
        "</TrustServiceProvider>"
    )


ELENCO = (
    "<TrustServiceStatusList xmlns='http://uri.etsi.org/02231/v2#'>"
    "<SchemeInformation><TSLSequenceNumber>224</TSLSequenceNumber>"
    "<ListIssueDateTime>2026-09-24T07:16:56Z</ListIssueDateTime>"
    "</SchemeInformation><TrustServiceProviderList>"
    + prestatore(
        "Certificatore Uno S.p.A.",
        servizio("CA/QC", "granted", "QUJD" * 20, "REVG"),
        servizio("CA/QC", "withdrawn", "R0hJ"),
        servizio("TSA/QTST", "granted", "SktM"),
    )
    + prestatore("Certificatore Due S.p.A.", servizio("CA/QC", "withdrawn"))
    + "</TrustServiceProviderList></TrustServiceStatusList>"
).encode()


def test_tiene_solo_i_servizi_qualificati_attivi():
    elenco, certificati = certificatori.leggi_elenco(ELENCO)
    assert elenco == certificatori.Elenco(
        emesso="2026-09-24T07:16:56Z", numero=224, servizi=1, certificatori=1
    )
    assert len(certificati) == 2
    primo = certificati[0].splitlines()
    assert primo[0] == "-----BEGIN CERTIFICATE-----"
    assert primo[1] == "QUJD" * 16 and primo[2] == "QUJD" * 4
    assert primo[-1] == "-----END CERTIFICATE-----"


def test_scarica_salva_certificati_e_notizie(tmp_path):
    origine = tmp_path / "TSL-IT.xml"
    origine.write_bytes(ELENCO)
    cartella = tmp_path / "dati"
    assert certificatori.notizie(cartella) is None
    elenco = certificatori.scarica(cartella, indirizzo=origine.as_uri())
    assert certificatori.notizie(cartella) == elenco
    pem = (cartella / certificatori.FILE_CERTIFICATI).read_text()
    assert pem.count("BEGIN CERTIFICATE") == 2
