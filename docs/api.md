# API reference

Generated from the docstrings in the package. The guides cover how these fit
together; this page is the exhaustive list.

Autodoc emits reStructuredText, which the markdown parser does not read, so
every directive below sits in an `eval-rst` block. Without it the page renders
the directive source as prose and the build still succeeds.

```{eval-rst}
.. automodule:: mx_remote
```

## Client

`Remote` owns the socket, the device registry and the background probe that
keeps both in step with the mesh.

```{eval-rst}
.. automodule:: mx_remote.remote.Remote
   :members:
```

## Devices, bays and callbacks

A client works against these types rather than the classes implementing them:
they are what the registry hands out and what a callback receives.

```{eval-rst}
.. automodule:: mx_remote.Interface
   :members:
```

## Device identity

```{eval-rst}
.. automodule:: mx_remote.Uid
   :members:
```

## Remote-control keys and actions

The key and action codes a bay reports, and the target a key was aimed at.

```{eval-rst}
.. autoclass:: mx_remote.proto.Constants.RCKey
   :members:
   :undoc-members:

.. autoclass:: mx_remote.proto.Constants.RCAction
   :members:
   :undoc-members:

.. autoclass:: mx_remote.proto.Constants.RCType
   :members:
   :undoc-members:

.. autodata:: mx_remote.proto.Constants.MXR_PROTOCOL_VERSION
```
