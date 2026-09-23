create index watchlist_items_watchlist_user_idx
  on public.watchlist_items(watchlist_id, user_id);

create index portfolio_positions_portfolio_user_idx
  on public.portfolio_positions(portfolio_id, user_id);
