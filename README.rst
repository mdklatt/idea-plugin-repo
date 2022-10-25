################
idea-plugin-repo
################

|pages|

Static `GitHub Pages`_ site for a custom JetBrains IDEA `plugin repository`_
for the plugins at `github.com/mdklatt`_.


***********
Development
***********

Set up a development environment.

.. code-block:: console

    $ make dev


Build site content. Generated content is put in ``dist/`` by default. The
*config.toml* file controls content generation.

.. code-block:: console

    $ make build


**********
Deployment
**********

Pushes to ``main`` are automatically deployed to https://mdklatt.github.io/idea-plugin-repo
by `GitHub Actions`_.


.. _GitHub Pages: https://docs.github.com/en/pages
.. _plugin repository: https://plugins.jetbrains.com/docs/intellij/custom-plugin-repository
.. _github.com/mdklatt: https://github.com/mdklatt
.. _GitHub Actions: https://github.com/mdklatt/idea-plugin-repo/blob/main/.github/workflows/pages.yml
.. |pages| image:: https://github.com/mdklatt/idea-plugin-repo/actions/workflows/pages.yml/badge.svg
    :alt: Pages Workflow
    :target: `GitHub Actions`_
