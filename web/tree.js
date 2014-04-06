/** @jsx React.DOM */

var Tree = React.createClass({
    loadTreeFromServer: function() {
        $.getJSON("fetchTree", _.bind(function(data) {
            this.setState({children: data})
        }, this));
    },

    getInitialState: function() {
        return {children: {}};
    },

    componentWillMount: function() {
        this.loadTreeFromServer();
        setInterval(this.loadTreeFromServer, this.props.pollInterval)
    },

    render: function() {
        console.log(this.state.children);
        return (
            <div className="tree">
                <TreeFolder name={this.props.root} children={this.state.children} />
            </div>
        );
    }
});

var TreeFolder = React.createClass({

    handleClick: function() {
        var items = this.refs.children.getDOMNode();
        $(items).toggle()
    },

    render: function() {
        var children = _.map(this.props.children, function(children, name) {
            if (_.isString(children)) {
                return <li> <TreeItem name={name} path={children} /> </li>;
            } else {
                return <li> <TreeFolder name={name} children={children} /> </li>;
            }
        });

        return (
            <div className="treeFolder">
              <p onClick={this.handleClick}> {this.props.name} </p>
              <ul ref="children">
                {children}
              </ul>
            </div>
        );
    }
});

var TreeItem = React.createClass({
    handleClick: function() {
        $.ajax({
            url: 'fetchFile',
            data: this.props.path,
            dataType: 'json',
            success: function(link) {
                if (link['link'].length > 0) {
                    window.open(link['link'], '_newtab');
                }
            }
        });
    },

    render: function() {
        return (
            <div className="treeItem">
                <a onClick={this.handleClick}> {this.props.name} </a>
            </div>
        );
    }
});

React.renderComponent(
        <Tree root="/" pollInterval={5000} />,
        $('#tree')[0]);
