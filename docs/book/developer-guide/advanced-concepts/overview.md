---
description: What are materializers, services, step contexts, and step fixtures?
---

# Advanced Concepts

The previous sections on [Steps and Pipelines](../steps-pipelines/steps-and-pipelines.md)
and [Stacks, Profiles, Repositories](../stacks-profiles-repositories/stacks_profiles_repositories.md)
already cover most of the concepts you will need for developing ML workflows
with ZenML.

However, there are a few additional concepts that you might or might not
encounter throughout your journey, about which you can learn more here.

In particular, these concepts might be helpful when developing custom 
components or when trying to understand the inner workings of ZenML in detail.

## List of Advanced Concepts

* [Materializers](developer-guide/materializer.md) define how artifacts are
saved and loaded at the end/beginning of steps. There already exist built-in
materializers for most common datatypes, but you might need to build a custom
materializer if one of your steps outputs a custom or unsupported class.
* [Services](developer-guide/manage-external-services.md) are long-lived
external processes that persist beyond the execution of your pipeline runs.
Examples are the services related to deployed models, or the UIs of some
visualization tools like TensorBoard.
* [Step Contexts and Step Fixtures](developer-guide/fetching-historic-runs.md)
allow you to access the repository (including the stack information) from
within a pipeline step. This can, for instance, be used to load the best 
performing prior model to compare newly trained models against.