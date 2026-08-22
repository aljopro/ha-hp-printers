"""Tests for the fixture anonymizer.

The anonymizer is what stands between a capture from someone's printer and
a public repository, so it gets the same treatment as runtime code. These
tests go through ``anonymize_file`` -- the entry point ``main`` uses -- so
a fix here cannot be undone by a second copy of the pipeline living in the
command-line path.
"""

from pathlib import Path

from defusedxml import ElementTree as DefusedET

from scripts.anonymize_ledm import anonymize_file


def _write(tmp_path: Path, name: str, xml: str) -> Path:
    """Write an XML document and return its path."""
    path = tmp_path / name
    path.write_text(xml.strip(), encoding="utf-8")
    return path


def _text(path: Path, tag: str) -> list[str]:
    """Return the text of every element with this local name."""
    root = DefusedET.fromstring(path.read_text(encoding="utf-8"))
    return [
        node.text
        for node in root.iter()
        if node.tag.rpartition("}")[2] == tag and node.text
    ]


def test_product_number_keeps_the_model_and_is_not_re_anonymized(
    tmp_path: Path,
) -> None:
    """ProductNumber becomes the model name and stays that way.

    The identifier pass would otherwise overwrite the substitution with its
    own placeholder, throwing away the one detail that makes a fixture
    recognizable.
    """
    source = _write(
        tmp_path,
        "DevMgmt_ProductConfigDyn.xml",
        """
        <ProductConfigDyn>
          <ProductInformation>
            <MakeAndModel>HP Color LaserJet MFP M182nw</MakeAndModel>
            <ProductNumber>7KW55A</ProductNumber>
            <SerialNumber>VNB3M40504</SerialNumber>
          </ProductInformation>
        </ProductConfigDyn>
        """,
    )
    target = tmp_path / "out.xml"

    anonymize_file(source, target)

    assert _text(target, "ProductNumber") == ["HP Color LaserJet MFP M182nw"]
    assert _text(target, "SerialNumber") == ["SN-ANON-0000"]


def test_network_identifiers_are_scrubbed(tmp_path: Path) -> None:
    """IOConfigDyn names the host four ways and carries the MAC twice."""
    source = _write(
        tmp_path,
        "DevMgmt_IOConfigDyn.xml",
        """
        <IOConfigDyn>
          <IOAdaptorConfig>
            <ApplicationConfig>
              <ApplicationServiceName>HP LaserJet (2E7F3D)</ApplicationServiceName>
              <DomainName>NPI2E7F3D.local.</DomainName>
            </ApplicationConfig>
            <NetworkAdaptorConfig>
              <CurrentHostname>NPI2E7F3D</CurrentHostname>
              <DefaultHostname>NPI2E7F3D</DefaultHostname>
              <BOOTP_DHCPv4SuppliedHostname>NPI2E7F3D</BOOTP_DHCPv4SuppliedHostname>
              <HardwareAddress>7c57582e7f3d</HardwareAddress>
              <IPAddress>192.168.0.64</IPAddress>
              <DefaultGateway>192.168.0.1</DefaultGateway>
              <SubnetMask>255.255.255.0</SubnetMask>
              <IPAddress>FE80::7E57:58FF:FE2E:7F3D</IPAddress>
            </NetworkAdaptorConfig>
          </IOAdaptorConfig>
        </IOConfigDyn>
        """,
    )
    target = tmp_path / "out.xml"

    anonymize_file(source, target)
    body = target.read_text(encoding="utf-8")

    for leaked in ("NPI2E7F3D", "7c57582e7f3d", "2E7F3D", "192.168.0."):
        assert leaked not in body, f"{leaked} survived anonymization"
    assert _text(target, "HardwareAddress") == ["000000000000"]
    # A netmask must stay a netmask: rewriting it as an address would read
    # as a parser bug when someone later debugs against the fixture.
    assert _text(target, "SubnetMask") == ["255.255.255.0"]
    assert "2001:db8::1" in body


def test_values_that_only_look_like_addresses_are_left_alone(tmp_path: Path) -> None:
    """The link mode reads like an IPv6 fragment; it must survive intact."""
    source = _write(
        tmp_path,
        "DevMgmt_IOConfigDyn.xml",
        """
        <IOConfigDyn>
          <NetworkAdaptorConfig>
            <SpeedDuplexNegotiationMode>100TX_FULL</SpeedDuplexNegotiationMode>
            <NetworkStatus>ready</NetworkStatus>
          </NetworkAdaptorConfig>
        </IOConfigDyn>
        """,
    )
    target = tmp_path / "out.xml"

    anonymize_file(source, target)

    assert _text(target, "SpeedDuplexNegotiationMode") == ["100TX_FULL"]
    assert _text(target, "NetworkStatus") == ["ready"]
