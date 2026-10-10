"""The one owner of this repository's TLS trust-anchor rule.

``ssl.create_default_context()`` finds no CA certificates in some interpreters on some
systems, this machine included: it answers ``cert_store_stats()['x509_ca'] == 0`` while
the Debian bundle exists at ``/etc/ssl/certs/ca-certificates.crt``.  A context with no
anchors still has ``verify_mode == CERT_REQUIRED``; every handshake then fails, and the
caller reports it as a network fault.

Every HTTPS call in this repository asks this module for its context, so the rule lives
once.  Standard library only, and no import from the repository.
"""
import os
import ssl

#: The system trust-anchor files, in the order this machine tries them.
CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu, Arch, NixOS
              "/etc/pki/tls/certs/ca-bundle.crt",     # Fedora, RHEL
              "/etc/ssl/cert.pem")                    # macOS, Alpine, BSDs


def bundle_path(paths=CA_BUNDLES):
    """The first path in ``paths`` that names an existing file, else ``None``."""
    for path in paths:
        if os.path.isfile(path):
            return path
    return None


def trusted_context():
    """The default verifying context, with a system bundle only when it found none.

    Some standalone Python builds (uv's, for one) find no CA certificates on some
    systems; then load the system bundle.  Certificate verification is never turned
    off.  ``check_hostname`` and ``verify_mode`` stay at the defaults of
    :func:`ssl.create_default_context`.
    """
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"]:
        bundle = bundle_path()
        if bundle:
            context.load_verify_locations(cafile=bundle)
    return context
