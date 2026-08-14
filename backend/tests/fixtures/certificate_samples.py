"""판독 규칙 회귀 테스트용 고정 인증서 텍스트.

실제 인증서 원문은 거래처 정보가 들어 있어 저장소에 넣을 수 없다. 대신 기관별
양식의 뼈대 — 기관명 표기, 인증번호 형식, 날짜 라벨 — 를 남긴 합성 텍스트를 쓴다.

이 파일의 목적은 "판독이 정확한가"가 아니라 "판독 결과가 리팩토링 전후로 같은가"다.
값을 고치면 골든이 깨지는 것이 정상이니, 샘플은 함부로 수정하지 말고 추가만 한다.
"""

from __future__ import annotations

# (case_id, filename, raw_text)
SAMPLES: list[tuple[str, str, str]] = [
    (
        "jakim_malaysia",
        "SAMPLE-JAKIM-2027.pdf",
        """
        JABATAN KEMAJUAN ISLAM MALAYSIA
        MALAYSIAN HALAL STANDARD MS1500:2019
        HALAL CERTIFICATE

        Reference No: JAKIM/(S)/(14.00)/599/2/1-12345
        Company: SAMPLE FOOD SDN BHD
        Product: SAMPLE SEASONING POWDER

        Date of Issue  : 01 March 2025
        Date of Expiry : 28 February 2027
        """,
    ),
    (
        "muis_singapore",
        "SAMPLE-MUIS_2026-05-31.pdf",
        """
        MAJLIS UGAMA ISLAM SINGAPURA
        ISLAMIC RELIGIOUS COUNCIL OF SINGAPORE
        HALAL CERTIFICATE

        Certificate No: PRN22020011873
        Name of Establishment: SAMPLE ASIA PACIFIC PTE LTD

        Valid until 31 May 2026
        """,
    ),
    (
        "cicot_thailand",
        "SAMPLE-CICOT.pdf",
        """
        THE CENTRAL ISLAMIC COUNCIL OF THAILAND
        SHEIKHUL ISLAM OF THAILAND
        HALAL CERTIFICATE

        Certificate Number: C-12-34567-89-01
        Manufacturer: SAMPLE THAI FOODS CO., LTD.

        Effective date : 15 January 2025
        Expired date   : 14 January 2027
        """,
    ),
    (
        "jma_japan",
        "SAMPLE-JMA.pdf",
        """
        JAPAN MUSLIM ASSOCIATION
        HALAL CERTIFICATE

        Certificate No. 284-TSRU/24
        Company Name: SAMPLE JAPAN CO., LTD.

        Date of Issue: 2024-04-01
        Date of Expiry: 2027-03-31
        """,
    ),
    (
        "ara_china",
        "SAMPLE-ARA.pdf",
        """
        ARA HALAL CERTIFICATION SERVICES CENTRE
        HALAL CERTIFICATE

        Certificate No: ARA-2025-0451
        Manufacturer: SAMPLE CHINA FOOD CO., LTD.

        Issued on   : 2025-02-10
        Valid until : 2027-02-09
        """,
    ),
    (
        "juhf_india",
        "SAMPLE-JUHF.pdf",
        """
        JUHF CERTIFICATION
        HALALHIND

        Certificate No: JUHF-0409-0240
        Firm: SAMPLE INDIA PRIVATE LIMITED

        Date of Issue : 12/06/2025
        Date of Expiry: 11/06/2027
        """,
    ),
    (
        "bpjph_indonesia",
        "[BPJPH] SAMPLE-2027.pdf",
        """
        BADAN PENYELENGGARA JAMINAN PRODUK HALAL
        REPUBLIK INDONESIA
        SERTIFIKAT HALAL

        Nomor: ID12345678901234567
        Nama Pelaku Usaha: PT SAMPLE INDONESIA

        Tanggal Terbit: 03 Maret 2025
        """,
    ),
    (
        "hffia_netherlands",
        "SAMPLE-HFFIA_2027-09-30.pdf",
        """
        HALAL FEED AND FOOD INSPECTION AUTHORITY
        HALAL VOEDING EN VOEDSEL
        www.halal.nl

        Certificate No: JRSRS/22012/H00249/080
        Company: SAMPLE B.V.

        Valid until: 30-09-2027
        """,
    ),
    (
        "hfce_europe",
        "SAMPLE-HFCE.pdf",
        """
        HALAL FOOD COUNCIL OF EUROPE
        www.hfce.eu

        Certificate Number: HFCE-2025-0099
        Producer: SAMPLE EUROPE GMBH

        Issue Date  : 2025-05-01
        Expiry Date : 2027-04-30
        """,
    ),
    (
        "ifanca_usa",
        "SAMPLE-IFANCA.pdf",
        """
        ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA
        HALAL CERTIFICATE

        Certificate No: IFANCA-778899
        Company: SAMPLE USA INC.

        Expiration Date: December 31, 2026
        """,
    ),
    (
        "kmf_korea",
        "SAMPLE-KMF.pdf",
        """
        KOREA MUSLIM FEDERATION
        한국이슬람교 중앙회
        할랄 인증서

        인증번호: KMF-2025-0123
        업체명: 샘플식품(주)

        유효기간: 2027-06-30
        """,
    ),
    (
        "unknown_org",
        "SAMPLE-UNKNOWN.pdf",
        """
        CERTIFICATE OF CONFORMITY

        This document certifies nothing in particular.
        Reference: XX-0000
        """,
    ),
    (
        "empty_text",
        "SAMPLE-EMPTY.pdf",
        "",
    ),
    (
        "tesseract_error",
        "SAMPLE-TESSERACT-FAIL.pdf",
        "[TESSERACT_ERROR] tesseract is not installed or it's not in your PATH",
    ),
]
