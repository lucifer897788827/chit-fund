import { Component } from "react";

import { PageErrorState } from "./page-state";

export class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);

    this.state = { error: null };
    this.handleRetry = this.handleRetry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  handleRetry() {
    this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return (
        <PageErrorState
          error="This page hit a problem, but you can try loading it again."
          title="Something went wrong."
          onRetry={this.handleRetry}
          retryLabel="Try again"
        />
      );
    }

    return this.props.children;
  }
}
