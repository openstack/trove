..
      Except where otherwise noted, this document is licensed under Creative
      Commons Attribution 3.0 License.  You can view the license at:

          https://creativecommons.org/licenses/by/3.0/


Installing API behind mod_wsgi
==============================

#. Install the Apache Service::

    Fedora/RHEL/CentOS:
      sudo dnf install httpd python3-mod_wsgi

    Debian/Ubuntu:
      sudo apt install apache2 libapache2-mod-wsgi-py3

#. Copy ``etc/apache2/trove`` under the apache sites::

    Fedora/RHEL/CentOS:
      sudo cp etc/apache2/trove /etc/httpd/conf.d/trove-api.conf

    Debian/Ubuntu:
      sudo cp etc/apache2/trove /etc/apache2/sites-available/trove-api.conf

#. Edit ``<apache-configuration-dir>/trove-api.conf`` according to installation
   and environment.

   * Modify the ``WSGIDaemonProcess`` directive to set the ``user`` and
     ``group`` values to appropriate user on your server.
   * Modify the ``WSGIScriptAlias`` directive to point to the
     trove/api/app_wsgi.py script.
   * Modify the ``Directory`` directive to set the path to the Trove API
     code.
   * Modify the ``ErrorLog and CustomLog`` to redirect the logs to the right
     directory.

#. Enable the apache trove site and reload::

    Fedora/RHEL/CentOS:
      sudo systemctl reload httpd

    Debian/Ubuntu:
      sudo a2ensite trove-api
      sudo systemctl reload apache2
