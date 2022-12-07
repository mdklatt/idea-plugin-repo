################
idea-plugin-repo
################

|pages|

This is the `GitHub Pages`_ source for `mdklatt.github.io/idea-plugin-repo`_,
a custom JetBrains IDEA `plugin repository`_ for:

- `Ansible Plugin`_
- `NetCDF Plugin`_
- `Remote Python Plugin`_



***********
Development
***********

Build content for local testing. Generated content is put in ``dist/``. The
*config.toml* file controls content generation.

.. code-block:: console

    $ make build


**********
Deployment
**********

Site content is published by GitHub Actions using the `Pages workflow`_.

Plugin updates
**************

Run the workflow manually when a plugin is updated, *e.g.* when a new version
is released.

Code updates
************

Code changes pushed to ``main`` will automatically trigger the workflow.


.. _GitHub Pages: https://docs.github.com/en/pages
.. _mdklatt.github.io/idea-plugin-repo: https://mdklatt.github.io/idea-plugin-repo
.. _Ansible Plugin: https://github.com/mdklatt/idea-ansible-plugin
.. _NetCDF Plugin: https://github.com/mdklatt/idea-netcdf-plugin
.. _Remote Python Plugin: https://github.com/mdklatt/idea-remotepython-plugin
.. _plugin repository: https://plugins.jetbrains.com/docs/intellij/custom-plugin-repository
.. _Pages workflow: https://github.com/mdklatt/idea-plugin-repo/actions/workflows/pages.yml
.. |pages| image:: https://github.com/mdklatt/idea-plugin-repo/actions/workflows/pages.yml/badge.svg
    :alt: Pages Workflow
    :target: `Pages workflow`_
