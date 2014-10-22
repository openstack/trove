If you would like to contribute to the development of OpenStack,
you must follow the steps documented at:

   http://wiki.openstack.org/HowToContribute#If_you.27re_a_developer

Once those steps have been completed, changes to OpenStack
should be submitted for review via the Gerrit tool, following
the workflow documented at:

   http://wiki.openstack.org/GerritWorkflow

Pull requests submitted through GitHub will be ignored.

Bugs should be filed on Launchpad, not GitHub:

   https://bugs.launchpad.net/trove

Code Reviews
------------

We value your contribution in reviewing code changes submitted by
others, as this helps increase the quality of the product as well.
The Trove project encourages the guidelines (below).

   - A rating of +1 on a code review is indicated if:

     * It is your opinion that the change, as proposed, should be
       considered for merging.


   - A rating of 0 on a code review is indicated if:

     * The reason why you believe that the proposed change needs
       improvement is merely an opinion,
     * You have a question, or need a clarification from the author,
     * The proposed change is functional but you believe that there is
       a different, better, or more appropriate way in which to
       acheive the end result being sought by the proposed change,
     * There is an issue of some kind with the Commit Message,
       including violations of the Commit Message guidelines,
     * There is a typographical or formatting error in the commit
       message or the body of the change itself,
     * There could be improvements in the test cases provided as part
       of the proposed change.


   - A rating of -1 on a code review is indicated if:

     * The reason why you believe that the proposed change needs
       improvement is irrefutable, or it is a widely shared opinion as
       indicated by a number of +0 comments,
     * The subject matter of the change (not the commit message)
       violates some well understood OpenStack procedure(s),
     * The change contains content that is demonstrably inappropriate,
     * The test cases do not exercise the change(s) being proposed,
     * You believe that the patch needs further work before it can be
       merged.


Some other reviewing guidelines:

   - In general, when in doubt, a rating of 0 is advised,
   - The code style guidelines accepted by the project are part of
     tox.ini, a violation of some other hacking rule(s), or pep8 is
     not a reason to -1 a change.

Other references:

   - https://wiki.openstack.org/wiki/CodeReviewGuidelines
   - https://wiki.openstack.org/wiki/How_To_Contribute
   - https://wiki.openstack.org/wiki/ReviewChecklist
   - https://wiki.openstack.org/wiki/GitCommitMessages
   - http://docs.openstack.org/developer/hacking/
   - https://review.openstack.org/#/c/116176/



