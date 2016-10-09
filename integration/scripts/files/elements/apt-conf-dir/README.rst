============
apt-conf-dir
============

This element overrides the default apt.conf.d directory for APT based systems.

Environment Variables
---------------------

DIB_APT_CONF_DIR:
   :Required: No
   :Default: None
   :Description: To override `DIB_APT_CONF_DIR`, set it to the path to your
                 apt.conf.d. The new apt.conf.d will take effect at build time
                 and run time.
   :Example: ``DIB_APT_CONF_DIR=/etc/apt/apt.conf``
