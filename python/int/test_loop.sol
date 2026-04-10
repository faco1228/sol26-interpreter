class Main : Object {
  run [ |
    _ := 5 timesRepeat: [ :i |
      s := i asString.
      _ := s print.
    ].
  ]
}
