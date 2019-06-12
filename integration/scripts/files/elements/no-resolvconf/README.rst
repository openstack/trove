This element clears out /etc/resolv.conf and prevents dhclient from populating
it with data from DHCP. This means that DNS resolution will not work from the
guest. This is OK because all outbound connections from the guest will
be based using raw IP addresses.

In addition we remove dns from the nsswitch.conf hosts setting.

This means that the guest never waits for DNS timeouts to occur.
