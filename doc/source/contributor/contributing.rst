============================
So You Want to Contribute...
============================

For general information on contributing to OpenStack, please check out the
`contributor guide <https://docs.openstack.org/contributors/>`_ to get started.
It covers all the basics that are common to all OpenStack projects: the accounts
you need, the basics of interacting with our Gerrit review system, how we
communicate as a community, etc.

Below will cover the more project specific information you need to get started
with Trove.

Communication
~~~~~~~~~~~~~~
.. This would be a good place to put the channel you chat in as a project; when/
   where your meeting is, the tags you prepend to your ML threads, etc.

- IRC channel: #openstack-trove
- Mailing list's prefix: [trove]
- Currently, we don't have team meeting given we have a small group of core
  reviewers and their timezones, the situation may change in the future.

Contacting the Core Team
~~~~~~~~~~~~~~~~~~~~~~~~~
.. This section should list the core team, their irc nicks, emails, timezones etc. If
   all this info is maintained elsewhere (i.e. a wiki), you can link to that instead of
   enumerating everyone here.

The list of current Trove core reviewers is available on `gerrit
<https://review.opendev.org/#/admin/groups/99,members>`_.

New Feature Planning
~~~~~~~~~~~~~~~~~~~~
.. This section is for talking about the process to get a new feature in. Some
   projects use blueprints, some want specs, some want both! Some projects
   stick to a strict schedule when selecting what new features will be reviewed
   for a release.

#. Talk to the team via IRC (meeting) or ML (with [trove] prefix) about
   the feature requested. We will discuss if a spec is needed based on
   the implementation complexity and the
   installation/configuration/upgrade/user-facing impacts.
#. If a spec is need, a patch needs to be submitted to `trove-specs repo
   <https://opendev.org/openstack/trove-specs>`_ before the code being
   reviewed.
#. Code implementation and review

Task Tracking
~~~~~~~~~~~~~~
.. This section is about where you track tasks- launchpad? storyboard? is there more
   than one launchpad project? what's the name of the project group in storyboard?

We track our tasks in `Storyboard
<https://storyboard.openstack.org/#!/project/openstack/trove>`_

If you're looking for some smaller, easier work item to pick up and get started
on, search for the 'low-hanging-fruit' tag.

Reporting a Bug
~~~~~~~~~~~~~~~
.. Pretty self explanatory section, link directly to where people should report bugs for
   your project.

You found an issue and want to make sure we are aware of it? You can do so
on `Storyboard <https://storyboard.openstack.org/#!/project/openstack/trove>`_.

Getting Your Patch Merged
~~~~~~~~~~~~~~~~~~~~~~~~~
.. This section should have info about what it takes to get something merged. Do
   you require one or two +2's before +W? Do some of your repos require unit test
   changes with all patches? etc.

Due to the small number of core reviewers of the Trove project, we only need
one +2 before ``Workflow +1``.

Project Team Lead Duties
------------------------
.. this section is where you can put PTL specific duties not already listed in
   the common PTL guide (linked below)  or if you already have them written
   up elsewhere, you can link to that doc here.

All common PTL duties are enumerated here in the `PTL guide
<https://docs.openstack.org/project-team-guide/ptl.html>`_.