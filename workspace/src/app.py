# ...

def main():
    # create app
    env_name = app.node.try_get_context("env")
    # load <env_name>.yaml
    # create application stages (storage, compute, ...) for each region
    app.synth()

# ...
